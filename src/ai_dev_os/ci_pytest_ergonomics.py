"""Round 4F/4G — pytest ergonomics + ci-targeted selection quality."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .ci_config import CIPolicy
from .ci_models import CIFailureClass, CIStageResult, CIStageStatus
from .ci_runner import CICommandError, run_ci_command
from .ci_secrets import redact_secrets
from .models import utc_now_iso

_FAILED_NODE_RE = re.compile(
    r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-|\s*$)"
)
_TOTAL_COV_RE = re.compile(
    r"^TOTAL\s+\d+\s+\d+\s+(\d+%)\s*$", re.MULTILINE
)


@dataclass
class PytestErgonomicsResult:
    stage: CIStageResult
    counts: dict[str, int | None]
    coverage_notes: list[str] = field(default_factory=list)


def coverage_module_available() -> bool:
    try:
        import coverage  # noqa: F401
    except ImportError:
        return False
    return True


def parse_failed_nodeids(text: str) -> list[str]:
    """Extract pytest node ids from FAILED/ERROR summary lines (order-preserving)."""
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        m = _FAILED_NODE_RE.match(stripped)
        if not m:
            continue
        node = m.group(1).strip()
        if not node or node in seen:
            continue
        # Prefer real node ids (file::name); skip bare labels
        if "::" not in node and not node.endswith(".py"):
            continue
        seen.add(node)
        found.append(node)
    return found


def _parse_counts(text: str) -> dict[str, int | None]:
    counts: dict[str, int | None] = {
        "tests_passed": None,
        "tests_failed": None,
        "tests_skipped": None,
    }
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
    return counts


def _redact_tail(text: str) -> str:
    lines = text.strip().splitlines()
    tail = "\n".join(lines[-20:])
    return redact_secrets(tail)[:2000]


def _finish_stage(
    stage_name: str,
    command_identity: str,
    started_at: str,
    t0: float,
    *,
    status: CIStageStatus,
    failure_class: CIFailureClass = CIFailureClass.NONE,
    summary: str = "",
    exit_status: int | None = None,
    timeout: bool = False,
    truncated: bool = False,
    blocker: bool = False,
    next_action: str = "",
    notes: list[str] | None = None,
    policy_decision: str = "allow",
    files: list[str] | None = None,
) -> CIStageResult:
    import time

    return CIStageResult(
        stage_name=stage_name,
        command_identity=command_identity,
        started_at=started_at,
        finished_at=utc_now_iso(),
        duration_seconds=round(time.perf_counter() - t0, 4),
        exit_status=exit_status,
        timeout_status=timeout,
        validation_status=status.value,
        failure_class=failure_class.value,
        sanitized_output_summary=summary[:4000],
        truncation_status=truncated,
        files_examined=list(files or []),
        policy_decision=policy_decision,
        blocker=blocker,
        next_action=next_action,
        notes=list(notes or []),
    )


def _build_primary_argv(
    *,
    paths: list[str] | None,
    use_coverage: bool,
    cov_data_file: Path | None,
) -> list[str]:
    path_args = list(paths or [])
    if use_coverage and cov_data_file is not None:
        return [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--data-file={cov_data_file}",
            "-m",
            "pytest",
            "-q",
            *path_args,
        ]
    return [sys.executable, "-m", "pytest", "-q", *path_args]


def _measure_coverage_notes(
    repo_root: Path,
    policy: CIPolicy,
    cov_data_file: Path,
    *,
    changed_py_files: list[str] | None,
) -> list[str]:
    notes: list[str] = []
    timeout = policy.clamp_timeout(None, default=60.0)
    try:
        report = run_ci_command(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                f"--data-file={cov_data_file}",
            ],
            cwd=repo_root,
            timeout=timeout,
            output_limit_bytes=policy.output_limit_bytes,
        )
    except CICommandError as exc:
        notes.append(f"coverage report failed: {exc}")
        return notes
    text = (report.stdout or "") + "\n" + (report.stderr or "")
    m = _TOTAL_COV_RE.search(text)
    if m:
        notes.append(f"coverage total: {m.group(1)}")
    else:
        notes.append("coverage measured but TOTAL line not parsed")

    if changed_py_files:
        includes = [p.replace("\\", "/") for p in changed_py_files if p.endswith(".py")]
        includes = [p for p in includes if (repo_root / p).is_file()]
        if includes:
            # coverage --include takes comma-separated patterns
            pattern = ",".join(includes)
            try:
                creport = run_ci_command(
                    [
                        sys.executable,
                        "-m",
                        "coverage",
                        "report",
                        f"--data-file={cov_data_file}",
                        f"--include={pattern}",
                    ],
                    cwd=repo_root,
                    timeout=timeout,
                    output_limit_bytes=policy.output_limit_bytes,
                )
            except CICommandError:
                return notes
            ctext = (creport.stdout or "") + "\n" + (creport.stderr or "")
            cm = _TOTAL_COV_RE.search(ctext)
            if cm:
                notes.append(f"coverage changed-files: {cm.group(1)}")
    return notes


def run_pytest_ergonomics(
    repo_root: Path,
    policy: CIPolicy,
    *,
    stage_name: str = "pytest_suite",
    paths: list[str] | None = None,
    isolate_flaky: bool = False,
    coverage: bool = False,
    changed_py_files: list[str] | None = None,
) -> PytestErgonomicsResult:
    """Run pytest with optional flaky isolation and coverage notes."""
    import time

    path_args = list(paths or [])
    identity = "python -m pytest -q"
    if path_args:
        identity = f"python -m pytest -q ({len(path_args)} path(s))"
    started_at = utc_now_iso()
    t0 = time.perf_counter()
    notes: list[str] = []
    coverage_notes: list[str] = []
    use_cov = False
    cov_data_file: Path | None = None

    if coverage:
        if coverage_module_available():
            use_cov = True
            cov_dir = repo_root / "workspace" / "ci_coverage"
            cov_dir.mkdir(parents=True, exist_ok=True)
            cov_data_file = cov_dir / ".coverage"
            identity = "coverage run -m pytest -q"
        else:
            coverage_notes.append("coverage not measured (install optional extra)")

    argv = _build_primary_argv(
        paths=path_args, use_coverage=use_cov, cov_data_file=cov_data_file
    )
    timeout = policy.clamp_timeout(None, default=policy.pytest_timeout_seconds)
    try:
        cmd = run_ci_command(
            argv,
            cwd=repo_root,
            timeout=timeout,
            output_limit_bytes=policy.output_limit_bytes,
        )
    except CICommandError as exc:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.COMMAND_REJECTED,
            summary=str(exc),
            blocker=True,
            policy_decision="deny",
            notes=coverage_notes,
        )
        return PytestErgonomicsResult(
            stage=stage,
            counts={
                "tests_passed": None,
                "tests_failed": None,
                "tests_skipped": None,
            },
            coverage_notes=coverage_notes,
        )

    text = (cmd.stdout or "") + "\n" + (cmd.stderr or "")
    counts = _parse_counts(text)

    if use_cov and cov_data_file is not None and cov_data_file.exists():
        coverage_notes.extend(
            _measure_coverage_notes(
                repo_root,
                policy,
                cov_data_file,
                changed_py_files=changed_py_files,
            )
        )

    if cmd.timed_out:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.TIMEOUT,
            failure_class=CIFailureClass.TIMEOUT,
            summary="pytest timed out",
            timeout=True,
            truncated=cmd.truncated,
            blocker=True,
            notes=notes + coverage_notes,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    if cmd.exit_code == 0:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.PASSED,
            summary=_redact_tail(text) or "pytest ok",
            exit_status=0,
            truncated=cmd.truncated,
            notes=notes + coverage_notes,
            files=path_args,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    # Primary failure
    if not isolate_flaky:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.TESTS_FAILED,
            summary=_redact_tail(text),
            exit_status=cmd.exit_code,
            truncated=cmd.truncated,
            blocker=True,
            next_action="fix failing tests before merge",
            notes=notes + coverage_notes,
            files=path_args,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    nodeids = parse_failed_nodeids(text)
    if not nodeids:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.TESTS_FAILED,
            summary=_redact_tail(text)
            + "\n[isolate-flaky] could not parse failed node ids; treating as real failure",
            exit_status=cmd.exit_code,
            truncated=cmd.truncated,
            blocker=True,
            next_action="fix failing tests before merge",
            notes=notes + coverage_notes,
            files=path_args,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    retry_argv = [sys.executable, "-m", "pytest", "-q", *nodeids]
    try:
        retry = run_ci_command(
            retry_argv,
            cwd=repo_root,
            timeout=timeout,
            output_limit_bytes=policy.output_limit_bytes,
        )
    except CICommandError as exc:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.COMMAND_REJECTED,
            summary=str(exc),
            blocker=True,
            policy_decision="deny",
            notes=notes + coverage_notes,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    retry_text = (retry.stdout or "") + "\n" + (retry.stderr or "")
    if retry.timed_out:
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.TIMEOUT,
            failure_class=CIFailureClass.TIMEOUT,
            summary="isolated flaky re-run timed out",
            timeout=True,
            truncated=retry.truncated,
            blocker=True,
            notes=notes + coverage_notes,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    if retry.exit_code != 0:
        still = parse_failed_nodeids(retry_text) or nodeids
        stage = _finish_stage(
            stage_name,
            identity,
            started_at,
            t0,
            status=CIStageStatus.FAILED,
            failure_class=CIFailureClass.TESTS_FAILED,
            summary=_redact_tail(text + "\n--- isolate-flaky retry ---\n" + retry_text),
            exit_status=retry.exit_code,
            truncated=cmd.truncated or retry.truncated,
            blocker=True,
            next_action="fix failing tests before merge",
            notes=notes
            + coverage_notes
            + [f"isolate-flaky: still failing after retry: {', '.join(still)}"],
            files=path_args,
        )
        return PytestErgonomicsResult(
            stage=stage, counts=counts, coverage_notes=coverage_notes
        )

    # Honesty rule: fail-then-pass → flaky_test_detected, never silent pass
    loud = (
        "FLAKY TEST DETECTED (honesty rule): the following node(s) failed once then "
        f"passed in isolation — NOT a silent pass: {', '.join(nodeids)}"
    )
    notes.append(loud)
    for node in nodeids:
        notes.append(f"flaky_node: {node}")
    stage = _finish_stage(
        stage_name,
        identity,
        started_at,
        t0,
        status=CIStageStatus.PASSED,
        failure_class=CIFailureClass.FLAKY_TEST_DETECTED,
        summary=_redact_tail(text + "\n--- isolate-flaky retry (passed) ---\n" + retry_text),
        exit_status=0,
        truncated=cmd.truncated or retry.truncated,
        blocker=False,
        next_action="investigate flaky tests; do not treat as clean pass",
        notes=notes + coverage_notes,
        files=path_args + nodeids,
        policy_decision="allow",
    )
    return PytestErgonomicsResult(
        stage=stage, counts=counts, coverage_notes=coverage_notes
    )


def list_changed_paths(repo_root: Path, base: str, head: str = "HEAD") -> list[str]:
    cmd = run_ci_command(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=repo_root,
        timeout=60.0,
        output_limit_bytes=1_000_000,
    )
    if cmd.timed_out or cmd.exit_code not in (0,):
        raise CICommandError(cmd.stderr or cmd.stdout or "git diff --name-only failed")
    out: list[str] = []
    for line in (cmd.stdout or "").splitlines():
        p = line.strip().replace("\\", "/")
        if p:
            out.append(p)
    return out


BROAD_IMPACT_NOTE = "broad impact, full suite recommended"


@dataclass
class TargetedSelection:
    """Result of ci-targeted path selection (Round 4G)."""

    paths: list[str]
    broad_impact: bool = False
    notes: list[str] = field(default_factory=list)


def is_broad_impact_path(path: str) -> bool:
    """Return True when a changed path must not be narrowly targeted."""
    norm = path.replace("\\", "/")
    if norm.startswith("config/") or norm == "config":
        return True
    if norm.startswith("schemas/") or norm == "schemas":
        return True
    if not norm.startswith("src/") or not norm.endswith(".py"):
        return False
    name = Path(norm).name
    return name in {"__init__.py", "cli.py", "models.py"}


def src_path_to_dotted_module(path: str) -> str | None:
    """Map ``src/pkg/mod.py`` → ``pkg.mod`` (None if not a src Python module)."""
    norm = path.replace("\\", "/")
    if not norm.startswith("src/") or not norm.endswith(".py"):
        return None
    rel = norm[len("src/") :]
    if rel.endswith("/__init__.py"):
        rel = rel[: -len("/__init__.py")]
    elif rel.endswith("__init__.py"):
        rel = ""
    else:
        rel = rel[: -len(".py")]
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return None
    return ".".join(parts)


def _text_references_module(text: str, dotted: str) -> bool:
    """Conservative stdlib regex: import/from lines referencing ``dotted``."""
    if not dotted or not text:
        return False
    escaped = re.escape(dotted)
    pattern = rf"(?:from\s+{escaped}\s+import\b|\bimport\s+{escaped}\b)"
    return re.search(pattern, text) is not None


def _iter_test_files(repo_root: Path) -> list[str]:
    tests_root = repo_root / "tests"
    if not tests_root.is_dir():
        return []
    out: list[str] = []
    for hit in sorted(tests_root.rglob("*.py")):
        if not hit.is_file():
            continue
        name = hit.name
        if not (name.startswith("test_") or name.endswith("_test.py")):
            continue
        out.append(hit.relative_to(repo_root).as_posix())
    return out


def select_targeted_tests(repo_root: Path, changed: list[str]) -> TargetedSelection:
    """Map changed files → targeted pytest paths + broad-impact fail-safe."""
    norms = [raw.replace("\\", "/") for raw in changed if raw and str(raw).strip()]
    if any(is_broad_impact_path(n) for n in norms):
        return TargetedSelection(
            paths=[],
            broad_impact=True,
            notes=[BROAD_IMPACT_NOTE],
        )

    targets: list[str] = []
    seen: set[str] = set()

    def _add(rel: str) -> None:
        norm = rel.replace("\\", "/")
        if norm in seen:
            return
        if (repo_root / norm).is_file():
            seen.add(norm)
            targets.append(norm)

    changed_modules: list[str] = []
    for norm in norms:
        name = Path(norm).name
        if norm.startswith("tests/") and norm.endswith(".py"):
            if name.startswith("test_") or name.endswith("_test.py"):
                _add(norm)
        if norm.startswith("src/") and norm.endswith(".py"):
            stem = Path(norm).stem
            if stem == "__init__":
                continue
            _add(f"tests/test_{stem}.py")
            _add(f"tests/{stem}_test.py")
            tests_root = repo_root / "tests"
            if tests_root.is_dir():
                for hit in tests_root.rglob(f"test_{stem}.py"):
                    _add(hit.relative_to(repo_root).as_posix())
                for hit in tests_root.rglob(f"{stem}_test.py"):
                    _add(hit.relative_to(repo_root).as_posix())
            dotted = src_path_to_dotted_module(norm)
            if dotted:
                changed_modules.append(dotted)

    if changed_modules:
        for test_rel in _iter_test_files(repo_root):
            if test_rel in seen:
                continue
            try:
                text = (repo_root / test_rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if any(_text_references_module(text, dotted) for dotted in changed_modules):
                _add(test_rel)

    return TargetedSelection(paths=targets, broad_impact=False, notes=[])


def select_targeted_test_paths(repo_root: Path, changed: list[str]) -> list[str]:
    """Deterministic mapping from changed files to targeted pytest paths."""
    return select_targeted_tests(repo_root, changed).paths
