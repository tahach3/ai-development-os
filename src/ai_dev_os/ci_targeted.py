"""Round 4F — targeted pytest fast-signal against a git base ref."""

from __future__ import annotations

from pathlib import Path

from .ci_config import CIConfigError, CIPolicy, load_ci_policy
from .ci_engine import _apply_verdict, _persist_run, exit_code_for_run
from .ci_models import (
    CI_POLICY_VERSION,
    CI_SCHEMA_VERSION,
    CIFailureClass,
    CIRun,
    CIRunState,
    CIStageResult,
    CIStageStatus,
    CITriggerType,
    new_ci_run_id,
)
from .ci_pytest_ergonomics import (
    list_changed_paths,
    run_pytest_ergonomics,
    select_targeted_test_paths,
)
from .ci_runner import CICommandError
from .git_safety import inspect_repo
from .models import utc_now_iso


class CITargetedError(RuntimeError):
    """Raised when ci-targeted cannot resolve the change set."""


def run_ci_targeted(
    repo_root: Path | None = None,
    *,
    base: str,
    head: str = "HEAD",
    policy: CIPolicy | None = None,
    isolate_flaky: bool = False,
    persist: bool | None = None,
) -> CIRun:
    """Run targeted pytest for files changed since ``base`` (fast signal only)."""
    if not base or not str(base).strip():
        raise CITargetedError("--base is required for ci-targeted")
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        pol = policy or load_ci_policy(root / "config" / "ci_policy.yaml")
    except CIConfigError:
        if policy is None:
            raise
        pol = policy

    run = CIRun(
        schema_version=CI_SCHEMA_VERSION,
        ci_policy_version=CI_POLICY_VERSION,
        run_id=new_ci_run_id(),
        repository_identity=str(root),
        compared_base_commit=base,
        trigger_type=CITriggerType.LOCAL.value,
        state=CIRunState.RUNNING.value,
        started_at=utc_now_iso(),
    )
    try:
        inspection = inspect_repo(root)
        run.starting_commit = inspection.head or ""
    except Exception:  # noqa: BLE001
        run.starting_commit = ""

    try:
        changed = list_changed_paths(root, base, head)
    except CICommandError as exc:
        raise CITargetedError(str(exc)) from exc

    targets = select_targeted_test_paths(root, changed)
    changed_py = [p for p in changed if p.endswith(".py")]

    if not targets:
        now = utc_now_iso()
        stage = CIStageResult(
            stage_name="pytest_targeted",
            command_identity="ci-targeted (no tests)",
            started_at=now,
            finished_at=now,
            validation_status=CIStageStatus.PASSED.value,
            failure_class=CIFailureClass.NONE.value,
            sanitized_output_summary="no targeted tests for change set",
            notes=["no targeted tests for change set"],
            files_examined=list(changed),
            policy_decision="allow",
        )
        run.stages.append(stage)
    else:
        ergo = run_pytest_ergonomics(
            root,
            pol,
            stage_name="pytest_targeted",
            paths=targets,
            isolate_flaky=isolate_flaky,
            coverage=False,
            changed_py_files=changed_py,
        )
        run.stages.append(ergo.stage)
        run.tests_passed = ergo.counts.get("tests_passed")
        run.tests_failed = ergo.counts.get("tests_failed")
        run.tests_skipped = ergo.counts.get("tests_skipped")

    run.finished_at = utc_now_iso()
    try:
        from datetime import datetime

        start = datetime.fromisoformat(run.started_at)
        end = datetime.fromisoformat(run.finished_at)
        run.duration_seconds = max(0.0, (end - start).total_seconds())
    except Exception:  # noqa: BLE001
        run.duration_seconds = 0.0
    _apply_verdict(run)
    # Targeted is advisory: never claim BLOCKED merge authority beyond pytest outcome
    if persist if persist is not None else False:
        _persist_run(root, pol, run)
    return run


def exit_code_for_targeted(run: CIRun) -> int:
    return exit_code_for_run(run)
