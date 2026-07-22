"""Round 4A local CI engine — deterministic stage pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .atomic_io import atomic_write_json
from .ci_config import CIConfigError, CIPolicy, load_ci_policy
from .ci_models import (
    CI_POLICY_VERSION,
    CI_SCHEMA_VERSION,
    STAGE_ORDER,
    CIFailureClass,
    CIRun,
    CIRunState,
    CIStageResult,
    CIStageStatus,
    CITriggerType,
    CIVerdict,
    new_ci_run_id,
)
from .ci_stages import STAGE_FUNCS
from .git_safety import inspect_repo
from .models import utc_now_iso


class CIEngineError(RuntimeError):
    """Raised for CI engine policy / usage errors."""


def _skipped_stage(name: str, reason: str) -> CIStageResult:
    now = utc_now_iso()
    return CIStageResult(
        stage_name=name,
        command_identity="skipped",
        started_at=now,
        finished_at=now,
        validation_status=CIStageStatus.SKIPPED.value,
        sanitized_output_summary=reason,
        policy_decision="skip",
        next_action="",
    )


def run_ci_check(
    repo_root: Path | None = None,
    *,
    policy: CIPolicy | None = None,
    skip_stages: Iterable[str] | None = None,
    only_stages: Iterable[str] | None = None,
    base_commit: str | None = None,
    trigger_type: str = CITriggerType.LOCAL.value,
    require_clean: bool | None = None,
    persist: bool | None = None,
) -> CIRun:
    """Execute fixed-order CI stages and return a normalized CIRun."""
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        pol = policy or load_ci_policy(root / "config" / "ci_policy.yaml")
    except CIConfigError:
        # Allow tests to inject policy; production expects file
        if policy is None:
            raise
        pol = policy

    skip = {s.strip() for s in (skip_stages or []) if s and s.strip()}
    only = {s.strip() for s in (only_stages or []) if s and s.strip()} or None
    unknown = (skip | (only or set())) - set(STAGE_ORDER)
    if unknown:
        raise CIEngineError(f"Unknown CI stage name(s): {sorted(unknown)}")

    run = CIRun(
        schema_version=CI_SCHEMA_VERSION,
        ci_policy_version=CI_POLICY_VERSION,
        run_id=new_ci_run_id(),
        repository_identity=str(root),
        compared_base_commit=base_commit,
        trigger_type=trigger_type,
        state=CIRunState.RUNNING.value,
        started_at=utc_now_iso(),
    )
    try:
        inspection = inspect_repo(root)
        run.starting_commit = inspection.head or ""
    except Exception:  # noqa: BLE001
        run.starting_commit = ""

    test_counts: dict[str, int | None] = {
        "tests_passed": None,
        "tests_failed": None,
        "tests_skipped": None,
    }

    for name in STAGE_ORDER:
        if only is not None and name not in only:
            run.stages.append(_skipped_stage(name, "not in --only-stages"))
            continue
        if name in skip:
            run.stages.append(_skipped_stage(name, "skipped by operator"))
            continue
        func = STAGE_FUNCS.get(name)
        if func is None:
            raise CIEngineError(f"Missing stage implementation: {name}")
        if name == "repo_identity":
            stage_result = func(root, pol, require_clean=require_clean)
        elif name == "pytest_suite":
            stage_result, counts = func(root, pol)
            test_counts.update(counts)
        else:
            stage_result = func(root, pol)
        assert isinstance(stage_result, CIStageResult)
        run.stages.append(stage_result)
        if stage_result.blocker or stage_result.validation_status in {
            CIStageStatus.FAILED.value,
            CIStageStatus.TIMEOUT.value,
            CIStageStatus.BLOCKED.value,
            CIStageStatus.ERROR.value,
        }:
            # Continue remaining stages for visibility except after identity deny
            if name == "repo_identity" and stage_result.blocker:
                for rest in STAGE_ORDER[STAGE_ORDER.index(name) + 1 :]:
                    run.stages.append(
                        _skipped_stage(rest, "skipped after repo_identity failure")
                    )
                break

    run.tests_passed = test_counts["tests_passed"]
    run.tests_failed = test_counts["tests_failed"]
    run.tests_skipped = test_counts["tests_skipped"]
    run.finished_at = utc_now_iso()
    try:
        from datetime import datetime

        start = datetime.fromisoformat(run.started_at)
        end = datetime.fromisoformat(run.finished_at)
        run.duration_seconds = max(0.0, (end - start).total_seconds())
    except Exception:  # noqa: BLE001
        run.duration_seconds = 0.0
    _apply_verdict(run)
    if persist if persist is not None else pol.persist_results:
        _persist_run(root, pol, run)
    return run


def _apply_verdict(run: CIRun) -> None:
    failures: list[str] = []
    human = False
    blocker = False
    notes: list[str] = []
    for stage in run.stages:
        if stage.failure_class and stage.failure_class != CIFailureClass.NONE.value:
            if stage.validation_status != CIStageStatus.SKIPPED.value:
                failures.append(stage.failure_class)
        if stage.failure_class == CIFailureClass.HUMAN_REVIEW_REQUIRED.value:
            human = True
        if stage.blocker:
            blocker = True
        notes.extend(stage.notes[:3])
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for f in failures:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    run.failure_classes = uniq
    run.human_review_required = human
    run.blocker = blocker
    run.sanitized_notes = notes[:20]

    hard = [
        s
        for s in run.stages
        if s.blocker
        or s.validation_status
        in {
            CIStageStatus.FAILED.value,
            CIStageStatus.TIMEOUT.value,
            CIStageStatus.BLOCKED.value,
            CIStageStatus.ERROR.value,
        }
    ]
    if hard:
        run.final_verdict = CIVerdict.FAIL.value
        run.state = CIRunState.FAILED.value
        run.policy_decision = "deny"
        run.next_action = hard[0].next_action or "fix failing CI stages"
    elif human:
        run.final_verdict = CIVerdict.HUMAN_REVIEW_REQUIRED.value
        run.state = CIRunState.COMPLETED.value
        run.policy_decision = "human_review"
        run.next_action = "human review required; no auto-merge"
    else:
        # pass_with_notes if any stage notes
        any_notes = any(s.notes for s in run.stages if s.validation_status == CIStageStatus.PASSED.value)
        run.final_verdict = (
            CIVerdict.PASS_WITH_NOTES.value if any_notes else CIVerdict.PASS.value
        )
        run.state = CIRunState.COMPLETED.value
        run.policy_decision = "allow"
        run.next_action = "ci ok; no automatic merge"


def _persist_run(root: Path, policy: CIPolicy, run: CIRun) -> None:
    out_dir = root / "workspace" / policy.results_dirname
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run.run_id}.json"
    atomic_write_json(path, run.to_dict())


def ci_run_to_json(run: CIRun) -> str:
    return json.dumps(run.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def exit_code_for_run(run: CIRun) -> int:
    if run.final_verdict in {CIVerdict.PASS.value, CIVerdict.PASS_WITH_NOTES.value}:
        return 0
    if run.final_verdict == CIVerdict.BLOCKED.value:
        return 2
    return 1
