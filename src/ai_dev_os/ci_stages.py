"""Individual Round 4A CI stage implementations."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

import yaml

from . import __version__ as package_version
from .ci_config import CIPolicy
from .ci_dependency_policy import check_dependency_policy
from .ci_models import CIFailureClass, CIStageResult, CIStageStatus
from .ci_runner import CICommandError, run_ci_command
from .ci_secrets import scan_files
from .git_safety import GitSafetyError, inspect_repo
from .models import utc_now_iso
from .project_registry import EQUITIFY_SENTINELS, ProjectRegistry, ProjectRegistryError


def _begin(stage_name: str, command_identity: str) -> tuple[CIStageResult, float]:
    result = CIStageResult(
        stage_name=stage_name,
        command_identity=command_identity,
        started_at=utc_now_iso(),
        validation_status=CIStageStatus.RUNNING.value,
    )
    return result, time.perf_counter()


def _finish(
    result: CIStageResult,
    started: float,
    *,
    status: CIStageStatus,
    failure_class: CIFailureClass = CIFailureClass.NONE,
    summary: str = "",
    exit_status: int | None = None,
    timeout: bool = False,
    truncated: bool = False,
    blocker: bool = False,
    next_action: str = "",
    files: list[str] | None = None,
    notes: list[str] | None = None,
    policy_decision: str = "allow",
) -> CIStageResult:
    result.finished_at = utc_now_iso()
    result.duration_seconds = round(time.perf_counter() - started, 4)
    result.validation_status = status.value
    result.failure_class = failure_class.value
    result.sanitized_output_summary = summary[:4000]
    result.exit_status = exit_status
    result.timeout_status = timeout
    result.truncation_status = truncated
    result.blocker = blocker
    result.next_action = next_action
    result.files_examined = list(files or [])
    result.notes = list(notes or [])
    result.policy_decision = policy_decision
    return result


def _list_tracked_files(repo_root: Path) -> list[str]:
    try:
        from .ci_runner import run_ci_command as _run

        res = _run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            timeout=30.0,
            output_limit_bytes=2_000_000,
        )
        if res.exit_code != 0 or res.timed_out:
            return []
        parts = [p for p in res.stdout.split("\x00") if p]
        return [p.replace("\\", "/") for p in parts]
    except CICommandError:
        return []


def stage_repo_identity(
    repo_root: Path, policy: CIPolicy, *, require_clean: bool | None = None
) -> CIStageResult:
    result, t0 = _begin("repo_identity", "git_safety.inspect_repo")
    try:
        inspection = inspect_repo(repo_root)
    except GitSafetyError as exc:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.REPO_IDENTITY_FAILED,
            summary=str(exc),
            blocker=True,
            next_action="fix repository identity before CI",
            policy_decision="deny",
        )
    if not inspection.is_repo:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.REPO_IDENTITY_FAILED,
            summary="path is not a git repository",
            blocker=True,
            policy_decision="deny",
        )
    clean_req = policy.require_clean_worktree if require_clean is None else require_clean
    notes = [
        f"branch={inspection.branch}",
        f"head={inspection.head}",
        f"dirty={inspection.dirty}",
    ]
    if clean_req and inspection.dirty:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.REPO_IDENTITY_FAILED,
            summary="worktree is dirty but require_clean_worktree is set",
            blocker=True,
            notes=notes,
            policy_decision="deny",
            next_action="commit or stash before CI",
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary=f"repo ok branch={inspection.branch} head={(inspection.head or '')[:12]}",
        exit_status=0,
        notes=notes,
    )


def stage_python_compile(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("python_compile", "python -m compileall")
    targets = []
    for name in ("src", "tests"):
        p = repo_root / name
        if p.is_dir():
            targets.append(str(p))
    if not targets:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.PYTHON_COMPILE_FAILED,
            summary="no src/ or tests/ directories to compile",
            blocker=True,
        )
    argv = [sys.executable, "-m", "compileall", "-q", *targets]
    try:
        cmd = run_ci_command(
            argv,
            cwd=repo_root,
            timeout=policy.clamp_timeout(None, default=policy.compile_timeout_seconds),
            output_limit_bytes=policy.output_limit_bytes,
        )
    except CICommandError as exc:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.COMMAND_REJECTED,
            summary=str(exc),
            blocker=True,
            policy_decision="deny",
        )
    if cmd.timed_out:
        return _finish(
            result,
            t0,
            status=CIStageStatus.TIMEOUT,
            failure_class=CIFailureClass.TIMEOUT,
            summary="compileall timed out",
            timeout=True,
            truncated=cmd.truncated,
            blocker=True,
        )
    if cmd.exit_code != 0:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.PYTHON_COMPILE_FAILED,
            summary=(cmd.stderr or cmd.stdout or "compile failed")[:2000],
            exit_status=cmd.exit_code,
            truncated=cmd.truncated,
            blocker=True,
            files=targets,
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary="compileall ok",
        exit_status=0,
        files=targets,
        truncated=cmd.truncated,
    )


def stage_pytest_suite(repo_root: Path, policy: CIPolicy) -> tuple[CIStageResult, dict[str, int | None]]:
    result, t0 = _begin("pytest_suite", "python -m pytest -q")
    argv = [sys.executable, "-m", "pytest", "-q"]
    counts: dict[str, int | None] = {
        "tests_passed": None,
        "tests_failed": None,
        "tests_skipped": None,
    }
    try:
        cmd = run_ci_command(
            argv,
            cwd=repo_root,
            timeout=policy.clamp_timeout(None, default=policy.pytest_timeout_seconds),
            output_limit_bytes=policy.output_limit_bytes,
        )
    except CICommandError as exc:
        return (
            _finish(
                result,
                t0,
                status=CIStageStatus.FAILED,
                failure_class=CIFailureClass.COMMAND_REJECTED,
                summary=str(exc),
                blocker=True,
                policy_decision="deny",
            ),
            counts,
        )
    text = (cmd.stdout or "") + "\n" + (cmd.stderr or "")
    for line in reversed(text.splitlines()):
        if "passed" in line or "failed" in line:
            pm = re.search(r"(\d+)\s+passed", line)
            fm = re.search(r"(\d+)\s+failed", line)
            sm = re.search(r"(\d+)\s+skipped", line)
            if pm or fm or sm:
                counts["tests_passed"] = int(pm.group(1)) if pm else 0
                counts["tests_failed"] = int(fm.group(1)) if fm else 0
                counts["tests_skipped"] = int(sm.group(1)) if sm else 0
                break
    if cmd.timed_out:
        return (
            _finish(
                result,
                t0,
                status=CIStageStatus.TIMEOUT,
                failure_class=CIFailureClass.TIMEOUT,
                summary="pytest timed out",
                timeout=True,
                truncated=cmd.truncated,
                blocker=True,
            ),
            counts,
        )
    if cmd.exit_code != 0:
        return (
            _finish(
                result,
                t0,
                status=CIStageStatus.FAILED,
                failure_class=CIFailureClass.TESTS_FAILED,
                summary=redact_tail(text),
                exit_status=cmd.exit_code,
                truncated=cmd.truncated,
                blocker=True,
                next_action="fix failing tests before merge",
            ),
            counts,
        )
    return (
        _finish(
            result,
            t0,
            status=CIStageStatus.PASSED,
            summary=redact_tail(text) or "pytest ok",
            exit_status=0,
            truncated=cmd.truncated,
        ),
        counts,
    )


def redact_tail(text: str) -> str:
    from .ci_secrets import redact_secrets

    lines = text.strip().splitlines()
    tail = "\n".join(lines[-20:])
    return redact_secrets(tail)[:2000]


def stage_git_diff_check(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("git_diff_check", "git diff --check")
    summaries: list[str] = []
    for argv in (["git", "diff", "--check"], ["git", "diff", "--check", "--cached"]):
        try:
            cmd = run_ci_command(
                argv,
                cwd=repo_root,
                timeout=policy.clamp_timeout(None, default=policy.default_timeout_seconds),
                output_limit_bytes=policy.output_limit_bytes,
            )
        except CICommandError as exc:
            return _finish(
                result,
                t0,
                status=CIStageStatus.FAILED,
                failure_class=CIFailureClass.COMMAND_REJECTED,
                summary=str(exc),
                blocker=True,
            )
        if cmd.timed_out:
            return _finish(
                result,
                t0,
                status=CIStageStatus.TIMEOUT,
                failure_class=CIFailureClass.TIMEOUT,
                summary="git diff --check timed out",
                timeout=True,
                blocker=True,
            )
        if cmd.exit_code not in (0, None) and cmd.exit_code != 0:
            return _finish(
                result,
                t0,
                status=CIStageStatus.FAILED,
                failure_class=CIFailureClass.GIT_DIFF_CHECK_FAILED,
                summary=(cmd.stdout or cmd.stderr or "diff --check failed")[:2000],
                exit_status=cmd.exit_code,
                truncated=cmd.truncated,
                blocker=True,
            )
        summaries.append(" ".join(argv) + "=ok")
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary="; ".join(summaries),
        exit_status=0,
    )


def stage_schema_validation(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("schema_validation", "schemas/*.json structural")
    schema_dir = repo_root / "schemas"
    if not schema_dir.is_dir():
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.MALFORMED_SCHEMA,
            summary="schemas/ directory missing",
            blocker=True,
        )
    files: list[str] = []
    errors: list[str] = []
    for path in sorted(schema_dir.glob("*.json")):
        rel = path.relative_to(repo_root).as_posix()
        files.append(rel)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: JSON error {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{rel}: schema root must be object")
            continue
        if "$schema" not in data:
            errors.append(f"{rel}: missing $schema")
        if not any(k in data for k in ("properties", "$ref", "type", "oneOf", "allOf", "anyOf")):
            errors.append(f"{rel}: missing type/properties/$ref")
        if "title" not in data and "description" not in data:
            # soft note only
            pass
    if errors:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.MALFORMED_SCHEMA,
            summary="; ".join(errors)[:2000],
            blocker=True,
            files=files,
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary=f"validated {len(files)} schema files",
        exit_status=0,
        files=files,
    )


def stage_config_parse(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("config_parse", "config/* yaml/json parse")
    cfg = repo_root / "config"
    files: list[str] = []
    errors: list[str] = []
    if not cfg.is_dir():
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.MALFORMED_CONFIG,
            summary="config/ missing",
            blocker=True,
        )
    for path in sorted(cfg.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
            continue
        rel = path.relative_to(repo_root).as_posix()
        files.append(rel)
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                json.loads(text)
            else:
                yaml.safe_load(text)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{rel}: {exc}")
    if errors:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.MALFORMED_CONFIG,
            summary="; ".join(errors)[:2000],
            blocker=True,
            files=files,
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary=f"parsed {len(files)} config files",
        exit_status=0,
        files=files,
    )


def stage_project_registry(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("project_registry", "ProjectRegistry.load")
    example = repo_root / "config" / "projects.example.yaml"
    files = []
    try:
        if example.exists():
            files.append("config/projects.example.yaml")
            reg = ProjectRegistry(example)
            reg.load()
        live = repo_root / "config" / "projects.yaml"
        if live.exists():
            files.append("config/projects.yaml")
            ProjectRegistry(live).load()
    except ProjectRegistryError as exc:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.REGISTRY_INVALID,
            summary=str(exc),
            blocker=True,
            files=files,
            policy_decision="deny",
        )
    except Exception as exc:  # noqa: BLE001
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.REGISTRY_INVALID,
            summary=f"registry load error: {exc}",
            blocker=True,
            files=files,
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary="registry validation ok",
        exit_status=0,
        files=files,
    )


def stage_prohibited_paths(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    """Refuse Equitify *registration/roots*, not documentation that mentions disconnection."""
    result, t0 = _begin("prohibited_paths", "path sentinel scan")
    tracked = _list_tracked_files(repo_root)
    hits: list[str] = []
    # Tracked path segments that look like an Equitify project tree was vendored in.
    for rel in tracked:
        low = rel.lower().replace("\\", "/")
        parts = low.split("/")
        if "equitify-machine" in parts or "equitify_machine" in parts:
            hits.append(rel)
            continue
        # Absolute-looking external roots accidentally listed as tracked names
        for needle in policy.prohibited_path_substrings:
            n = needle.lower().replace("\\", "/").strip("/")
            if n and (low == n or low.startswith(n + "/") or f"/{n}/" in f"/{low}/"):
                if "equitify" in n:
                    hits.append(rel)
                    break
    # Registry files must not register Equitify (reuse ProjectRegistry loader).
    for candidate in (
        repo_root / "config" / "projects.example.yaml",
        repo_root / "config" / "projects.yaml",
    ):
        if not candidate.exists():
            continue
        try:
            ProjectRegistry(candidate).load()
        except ProjectRegistryError as exc:
            if any(s in str(exc).lower() for s in EQUITIFY_SENTINELS):
                hits.append(candidate.relative_to(repo_root).as_posix())
            else:
                hits.append(candidate.relative_to(repo_root).as_posix())
    if hits:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.PROHIBITED_PATH,
            summary=f"prohibited path/id markers: {hits[:20]}",
            blocker=True,
            files=sorted(set(hits)),
            policy_decision="deny",
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary="no prohibited Equitify registration/roots in tracked set",
        exit_status=0,
        files=[],
    )


def stage_package_version(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("package_version", "pyproject vs __version__")
    import tomllib

    pyproject = repo_root / "pyproject.toml"
    init_py = repo_root / "src" / "ai_dev_os" / "__init__.py"
    files = []
    try:
        files.append("pyproject.toml")
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        proj_ver = str((data.get("project") or {}).get("version", ""))
        files.append("src/ai_dev_os/__init__.py")
        init_text = init_py.read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_text)
        init_ver = m.group(1) if m else ""
        # Prefer on-disk init; package_version may be imported from installed egg
        if proj_ver != init_ver:
            return _finish(
                result,
                t0,
                status=CIStageStatus.FAILED,
                failure_class=CIFailureClass.PACKAGE_VERSION_MISMATCH,
                summary=f"pyproject={proj_ver!r} __init__={init_ver!r}",
                blocker=True,
                files=files,
            )
        notes = [f"version={proj_ver}"]
        if package_version != proj_ver:
            notes.append(
                f"imported package_version={package_version} differs (editable install may lag)"
            )
        return _finish(
            result,
            t0,
            status=CIStageStatus.PASSED,
            summary=f"version consistent: {proj_ver}",
            exit_status=0,
            files=files,
            notes=notes,
        )
    except Exception as exc:  # noqa: BLE001
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.PACKAGE_VERSION_MISMATCH,
            summary=str(exc),
            blocker=True,
            files=files,
        )


def stage_dependency_policy(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("dependency_policy", "check_dependency_policy")
    dep = check_dependency_policy(
        repo_root, prohibited_names=policy.prohibited_dependency_names
    )
    summary = (
        f"runtime={len(dep.runtime_deps)} dev={len(dep.dev_deps)}; "
        "vulnerability_scanning=false"
    )
    if not dep.ok:
        details = "; ".join(f"{f.name}:{f.category}" for f in dep.findings[:10])
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.DEPENDENCY_POLICY_VIOLATED,
            summary=f"{summary}; {details}",
            blocker=True,
            files=["pyproject.toml"],
            notes=[f.to_dict()["detail"] for f in dep.findings],
            policy_decision="deny",
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary=summary,
        exit_status=0,
        files=["pyproject.toml"],
        notes=dep.notes,
    )


def stage_secret_scan(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("secret_scan", "scan_files tracked")
    tracked = _list_tracked_files(repo_root)
    scan = scan_files(repo_root, tracked)
    if scan.findings:
        summary = "; ".join(
            f"{f.path}:{f.line_number}:{f.rule}" for f in scan.findings[:15]
        )
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.SECRET_PATTERN_DETECTED,
            summary=summary,
            blocker=True,
            files=scan.files_examined[:100],
            notes=[f.redacted_snippet for f in scan.findings[:10]],
            policy_decision="deny",
            next_action="remove or redact secrets; never commit credentials",
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary=f"scanned {len(scan.files_examined)} files; no secret patterns",
        exit_status=0,
        files=scan.files_examined[:100],
    )


def _matches_runtime_glob(rel: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch

    norm = rel.replace("\\", "/")
    for pat in patterns:
        p = pat.replace("\\", "/")
        if fnmatch(norm, p) or fnmatch(norm, p.rstrip("/")):
            return True
        # prefix form workspace/active/**
        if p.endswith("/**") and norm.startswith(p[:-3]):
            return True
    return False


def stage_runtime_artifacts(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("runtime_artifacts", "tracked runtime path check")
    tracked = _list_tracked_files(repo_root)
    bad: list[str] = []
    for rel in tracked:
        if rel.endswith(".gitkeep"):
            continue
        if _matches_runtime_glob(rel, policy.runtime_artifact_globs):
            bad.append(rel)
        low = rel.lower()
        if low.endswith(".pyc") or "/__pycache__/" in low.replace("\\", "/"):
            bad.append(rel)
    if bad:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.RUNTIME_ARTIFACT_DETECTED,
            summary=f"tracked runtime/private artifacts: {bad[:20]}",
            blocker=True,
            files=bad,
            policy_decision="deny",
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary="no unexpected tracked runtime artifacts",
        exit_status=0,
        files=[],
    )


def stage_doc_consistency(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("doc_consistency", "version markers")
    import tomllib

    files: list[str] = []
    notes: list[str] = []
    pyproject = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    ver = str((data.get("project") or {}).get("version", ""))
    files.append("pyproject.toml")
    # Soft checks on docs mentioning package version
    soft_fail = False
    for rel in (
        "README.md",
        "docs/ROADMAP.md",
        "docs/PROJECT_CHRONICLE.md",
    ):
        path = repo_root / rel
        if not path.exists():
            notes.append(f"missing {rel}")
            continue
        files.append(rel)
        text = path.read_text(encoding="utf-8")
        if ver and ver not in text:
            soft_fail = True
            notes.append(f"{rel} missing version {ver}")
    if soft_fail:
        return _finish(
            result,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.DOC_INCONSISTENCY,
            summary="; ".join(notes)[:2000],
            blocker=True,
            files=files,
            notes=notes,
            next_action="update docs to match package version",
        )
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary=f"doc markers ok for {ver}",
        exit_status=0,
        files=files,
        notes=notes,
    )


def stage_finalize(repo_root: Path, policy: CIPolicy) -> CIStageResult:
    result, t0 = _begin("finalize", "normalized_result")
    return _finish(
        result,
        t0,
        status=CIStageStatus.PASSED,
        summary="finalize placeholder; engine assembles run record",
        exit_status=0,
    )


STAGE_FUNCS: dict[str, Callable[..., CIStageResult | tuple[CIStageResult, dict]]] = {
    "repo_identity": stage_repo_identity,
    "python_compile": stage_python_compile,
    "pytest_suite": stage_pytest_suite,
    "git_diff_check": stage_git_diff_check,
    "schema_validation": stage_schema_validation,
    "config_parse": stage_config_parse,
    "project_registry": stage_project_registry,
    "prohibited_paths": stage_prohibited_paths,
    "package_version": stage_package_version,
    "dependency_policy": stage_dependency_policy,
    "secret_scan": stage_secret_scan,
    "runtime_artifacts": stage_runtime_artifacts,
    "doc_consistency": stage_doc_consistency,
    "finalize": stage_finalize,
}
