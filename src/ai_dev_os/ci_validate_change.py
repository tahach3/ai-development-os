"""Pull-request / change-range validation without executing change code."""

from __future__ import annotations

import re
import time
from pathlib import Path

import yaml

from .ci_boundaries import check_project_boundaries
from .ci_config import CIPolicy, load_ci_policy
from .ci_dependency_policy import check_dependency_policy
from .ci_models import (
    CIFailureClass,
    CITriggerType,
    CIVerdict,
    PRValidationFinding,
    PRValidationSummary,
    new_ci_run_id,
)
from .ci_runner import CICommandError, run_ci_command
from .ci_secrets import scan_files
from .ci_stages import _matches_runtime_glob
from .git_safety import inspect_repo
from .models import utc_now_iso
from .project_registry import EQUITIFY_SENTINELS


class ValidateChangeError(RuntimeError):
    """Raised when validate-change cannot inspect the requested range."""


def _git_name_status(repo_root: Path, base: str | None, head: str) -> list[tuple[str, str]]:
    """Return list of (status, path) for the change range."""
    if base:
        argv = ["git", "diff", "--name-status", f"{base}...{head}"]
    else:
        argv = ["git", "diff", "--name-status", "HEAD"]
        # include unstaged + untracked via status porcelain as supplement
    try:
        cmd = run_ci_command(argv, cwd=repo_root, timeout=60.0, output_limit_bytes=1_000_000)
    except CICommandError as exc:
        raise ValidateChangeError(str(exc)) from exc
    if cmd.timed_out or cmd.exit_code not in (0,):
        raise ValidateChangeError(cmd.stderr or cmd.stdout or "git diff failed")
    rows: list[tuple[str, str]] = []
    for line in (cmd.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1].replace("\\", "/")))
    if not base:
        # also untracked
        st = run_ci_command(
            ["git", "status", "--porcelain", "-u"],
            cwd=repo_root,
            timeout=30.0,
            output_limit_bytes=500_000,
        )
        for line in (st.stdout or "").splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip().replace("\\", "/")
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            status = line[:2].strip() or "M"
            rows.append((status, path))
    # dedupe preserving order
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for st, p in rows:
        if p not in seen:
            seen.add(p)
            out.append((st, p))
    return out


def _is_safety_critical(path: str, policy: CIPolicy) -> bool:
    norm = path.replace("\\", "/")
    for prefix in policy.safety_critical_path_prefixes:
        p = prefix.replace("\\", "/")
        if norm == p or norm.startswith(p.rstrip("/") + "/") or norm.startswith(p):
            return True
    return False


def _workflow_findings(repo_root: Path, paths: list[str]) -> list[PRValidationFinding]:
    findings: list[PRValidationFinding] = []
    for rel in paths:
        if not rel.startswith(".github/workflows/") or not rel.endswith((".yml", ".yaml")):
            continue
        path = repo_root / rel
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            findings.append(
                PRValidationFinding(
                    path=rel,
                    category="workflow",
                    severity="blocker",
                    summary=f"malformed workflow YAML: {exc}",
                    failure_class=CIFailureClass.MALFORMED_CONFIG.value,
                    blocker=True,
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        # Ignore YAML comments for capability bans (docs may say "no deploy").
        code_lines = [
            ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        perms = data.get("permissions") if isinstance(data, dict) else None
        if perms is None:
            findings.append(
                PRValidationFinding(
                    path=rel,
                    category="workflow_permissions",
                    severity="major",
                    summary="workflow missing explicit permissions block",
                    failure_class=CIFailureClass.UNSAFE_WORKFLOW.value,
                    human_review_required=True,
                )
            )
        elif isinstance(perms, dict):
            for key, val in perms.items():
                if str(val).lower() == "write":
                    findings.append(
                        PRValidationFinding(
                            path=rel,
                            category="workflow_permissions",
                            severity="blocker",
                            summary=f"write permission refused: {key}: write",
                            failure_class=CIFailureClass.UNSAFE_WORKFLOW.value,
                            blocker=True,
                            human_review_required=True,
                        )
                    )
        if re.search(r"\$\{\{\s*secrets\.", code_text):
            findings.append(
                PRValidationFinding(
                    path=rel,
                    category="workflow_secrets",
                    severity="blocker",
                    summary="workflow references secrets.*; Round 4A forbids repository secrets",
                    failure_class=CIFailureClass.UNSAFE_WORKFLOW.value,
                    blocker=True,
                )
            )
        for banned in (
            "auto-merge",
            "automerging",
            "gh pr merge",
            "github.rest.pulls.merge",
            "peaceiris/actions-gh-pages",
            "actions/deploy-pages",
        ):
            if banned.lower() in code_text.lower():
                findings.append(
                    PRValidationFinding(
                        path=rel,
                        category="workflow_deploy_or_merge",
                        severity="blocker",
                        summary=f"forbidden workflow capability hint: {banned}",
                        failure_class=CIFailureClass.UNSAFE_WORKFLOW.value,
                        blocker=True,
                    )
                )
        for provider in ("openai", "anthropic", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if provider.lower() in code_text.lower():
                findings.append(
                    PRValidationFinding(
                        path=rel,
                        category="workflow_live_provider",
                        severity="blocker",
                        summary=f"live provider credential/reference refused: {provider}",
                        failure_class=CIFailureClass.UNSAFE_WORKFLOW.value,
                        blocker=True,
                    )
                )
    return findings


def validate_change(
    repo_root: Path | None = None,
    *,
    base: str | None = None,
    head: str = "HEAD",
    policy: CIPolicy | None = None,
) -> PRValidationSummary:
    """Validate a proposed commit range/diff without executing changed code."""
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    pol = policy or load_ci_policy(root / "config" / "ci_policy.yaml")
    t0 = time.perf_counter()
    started = utc_now_iso()
    inspection = inspect_repo(root)
    summary = PRValidationSummary(
        run_id=new_ci_run_id(),
        repository_identity=str(root),
        starting_commit=inspection.head or head,
        compared_base_commit=base,
        trigger_type=CITriggerType.VALIDATE_CHANGE.value,
        started_at=started,
    )

    try:
        rows = _git_name_status(root, base, head)
    except ValidateChangeError as exc:
        summary.findings.append(
            PRValidationFinding(
                path="",
                category="git",
                severity="blocker",
                summary=str(exc),
                failure_class=CIFailureClass.INTERNAL_ERROR.value,
                blocker=True,
            )
        )
        summary.finished_at = utc_now_iso()
        summary.duration_seconds = round(time.perf_counter() - t0, 4)
        summary.final_verdict = CIVerdict.FAIL.value
        summary.blocker = True
        summary.failure_classes = [CIFailureClass.INTERNAL_ERROR.value]
        return summary

    paths = [p for _, p in rows]
    summary.files_examined = paths

    for status, path in rows:
        low = path.lower().replace("\\", "/")
        parts = low.split("/")
        if "equitify-machine" in parts or "equitify_machine" in parts:
            summary.findings.append(
                PRValidationFinding(
                    path=path,
                    category="prohibited_path",
                    severity="blocker",
                    summary="Equitify path refused",
                    failure_class=CIFailureClass.PROHIBITED_PATH.value,
                    blocker=True,
                )
            )
        for s in EQUITIFY_SENTINELS:
            # only if path itself is the sentinel project
            if s in parts:
                summary.findings.append(
                    PRValidationFinding(
                        path=path,
                        category="prohibited_path",
                        severity="blocker",
                        summary=f"Equitify identifier in path: {s}",
                        failure_class=CIFailureClass.PROHIBITED_PATH.value,
                        blocker=True,
                    )
                )
        if _matches_runtime_glob(path, pol.runtime_artifact_globs) and not path.endswith(
            ".gitkeep"
        ):
            summary.findings.append(
                PRValidationFinding(
                    path=path,
                    category="runtime_artifact",
                    severity="blocker",
                    summary="runtime/private artifact must not be committed",
                    failure_class=CIFailureClass.RUNTIME_ARTIFACT_DETECTED.value,
                    blocker=True,
                )
            )
        if _is_safety_critical(path, pol):
            summary.findings.append(
                PRValidationFinding(
                    path=path,
                    category="safety_critical",
                    severity="major",
                    summary="safety-critical policy/path change requires human review",
                    failure_class=CIFailureClass.HUMAN_REVIEW_REQUIRED.value,
                    human_review_required=True,
                    blocker=False,
                )
            )

    # Secret scan on proposed file contents currently on disk (not executing them)
    existing = [p for p in paths if (root / p).is_file()]
    scan = scan_files(root, existing)
    for f in scan.findings:
        summary.findings.append(
            PRValidationFinding(
                path=f.path,
                category="secret_pattern",
                severity="blocker",
                summary=f"secret-like pattern ({f.rule}) at line {f.line_number}: {f.redacted_snippet}",
                failure_class=CIFailureClass.SECRET_PATTERN_DETECTED.value,
                blocker=True,
            )
        )

    # Schema/config parse for touched files
    for path in existing:
        full = root / path
        if path.startswith("schemas/") and path.endswith(".json"):
            try:
                import json

                data = json.loads(full.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "$schema" not in data:
                    summary.findings.append(
                        PRValidationFinding(
                            path=path,
                            category="schema",
                            severity="blocker",
                            summary="schema incompatible or missing $schema",
                            failure_class=CIFailureClass.MALFORMED_SCHEMA.value,
                            blocker=True,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                summary.findings.append(
                    PRValidationFinding(
                        path=path,
                        category="schema",
                        severity="blocker",
                        summary=f"malformed schema: {exc}",
                        failure_class=CIFailureClass.MALFORMED_SCHEMA.value,
                        blocker=True,
                    )
                )
        if path.startswith("config/") and path.endswith((".yaml", ".yml", ".json")):
            try:
                text = full.read_text(encoding="utf-8")
                if path.endswith(".json"):
                    import json

                    json.loads(text)
                else:
                    yaml.safe_load(text)
            except Exception as exc:  # noqa: BLE001
                summary.findings.append(
                    PRValidationFinding(
                        path=path,
                        category="config",
                        severity="blocker",
                        summary=f"malformed config: {exc}",
                        failure_class=CIFailureClass.MALFORMED_CONFIG.value,
                        blocker=True,
                    )
                )

    summary.findings.extend(_workflow_findings(root, existing))

    boundary = check_project_boundaries(
        paths=paths,
        policy=pol,
        repo_root=root,
        read_content=True,
    )
    for bf in boundary.findings:
        summary.findings.append(
            PRValidationFinding(
                path=bf.path,
                category="project_boundary",
                severity="blocker",
                summary=bf.detail,
                failure_class=bf.failure_class,
                blocker=bf.blocker,
            )
        )

    if any(p == "pyproject.toml" or p.endswith("/pyproject.toml") for p in paths):
        dep = check_dependency_policy(root, prohibited_names=pol.prohibited_dependency_names)
        for f in dep.findings:
            summary.findings.append(
                PRValidationFinding(
                    path="pyproject.toml",
                    category="dependency_policy",
                    severity="blocker" if f.blocker else "major",
                    summary=f.detail,
                    failure_class=CIFailureClass.DEPENDENCY_POLICY_VIOLATED.value,
                    blocker=f.blocker,
                )
            )
        # package version consistency quick check
        try:
            import tomllib
            import re as _re

            data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
            ver = str((data.get("project") or {}).get("version", ""))
            init = (root / "src" / "ai_dev_os" / "__init__.py").read_text(encoding="utf-8")
            m = _re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init)
            if m and m.group(1) != ver:
                summary.findings.append(
                    PRValidationFinding(
                        path="pyproject.toml",
                        category="package_version",
                        severity="blocker",
                        summary=f"version mismatch pyproject={ver} init={m.group(1)}",
                        failure_class=CIFailureClass.PACKAGE_VERSION_MISMATCH.value,
                        blocker=True,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            summary.findings.append(
                PRValidationFinding(
                    path="pyproject.toml",
                    category="package_version",
                    severity="major",
                    summary=str(exc),
                    failure_class=CIFailureClass.PACKAGE_VERSION_MISMATCH.value,
                    human_review_required=True,
                )
            )

    # Never auto-approve/merge
    summary.auto_approve = False
    summary.auto_merge = False
    summary.human_review_required = any(f.human_review_required for f in summary.findings)
    summary.blocker = any(f.blocker for f in summary.findings)
    classes: list[str] = []
    for f in summary.findings:
        if f.failure_class and f.failure_class not in classes:
            classes.append(f.failure_class)
    summary.failure_classes = classes
    summary.finished_at = utc_now_iso()
    summary.duration_seconds = round(time.perf_counter() - t0, 4)

    if summary.blocker:
        summary.final_verdict = CIVerdict.FAIL.value
        summary.policy_decision = "deny"
        summary.next_action = "fix blockers; no automatic merge"
    elif summary.human_review_required:
        summary.final_verdict = CIVerdict.HUMAN_REVIEW_REQUIRED.value
        summary.policy_decision = "human_review"
        summary.next_action = "human review required; no automatic approve/merge"
    else:
        summary.final_verdict = CIVerdict.PASS.value
        summary.policy_decision = "report_only"
        summary.next_action = "validation ok; no automatic merge"

    return summary


def exit_code_for_pr_summary(summary: PRValidationSummary) -> int:
    if summary.final_verdict == CIVerdict.PASS.value:
        return 0
    if summary.final_verdict == CIVerdict.HUMAN_REVIEW_REQUIRED.value:
        return 0  # classified for humans; not sole auto-fail
    return 1
