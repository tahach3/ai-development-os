"""Task/plan linkage and implementation eligibility gates."""

from __future__ import annotations

from pathlib import Path

from .approval import plan_is_implementable
from .fingerprints import fingerprint_plan, fingerprint_task
from .git_safety import GitSafetyError, inspect_repo
from .models import Plan, PlanStatus, Task, TaskStatus
from .project_registry import ProjectRegistry, ProjectRegistryError
from .validation import ValidationError


class GateError(ValidationError):
    """Raised when a lifecycle gate blocks progression."""


def assert_task_active(task: Task) -> None:
    if task.status is TaskStatus.BLOCKED:
        raise GateError(f"Task {task.id} is blocked: {task.blocked_reason or 'no reason'}")
    if task.status is TaskStatus.CANCELLED:
        raise GateError(f"Task {task.id} is cancelled")


def assert_can_create_plan(task: Task) -> None:
    assert_task_active(task)
    if task.status is not TaskStatus.READY_FOR_PLANNING:
        raise GateError(
            f"Task must be ready_for_planning before creating a plan "
            f"(got {task.status.value})"
        )


def assert_can_mark_planned(task: Task, plan: Plan) -> None:
    assert_task_active(task)
    if plan.status not in (PlanStatus.DRAFT, PlanStatus.READY_FOR_APPROVAL, PlanStatus.APPROVED):
        raise GateError(f"Plan status {plan.status.value} cannot mark task planned")
    # Valid plan must exist (validated separately); task moves planned on submit.


def assert_can_prepare_implementation_handoff(
    task: Task,
    plan: Plan | None,
    project_root: str | Path,
    *,
    require_clean_worktree: bool = True,
) -> None:
    assert_task_active(task)
    if task.status not in (
        TaskStatus.APPROVED_FOR_IMPLEMENTATION,
        TaskStatus.IMPLEMENTING,
        TaskStatus.VALIDATING,
        TaskStatus.REVIEW_FAILED,
    ):
        raise GateError(
            "Implementation handoff requires approved_for_implementation "
            f"(or repair states); got {task.status.value}"
        )
    if plan is None:
        raise GateError("No approved plan linked for implementation handoff")
    if not plan_is_implementable(plan):
        raise GateError(
            "Plan is not implementable: must be approved with matching fingerprint"
        )
    if plan.task_id != task.id:
        raise GateError("Plan task_id does not match task")

    # Task scope fingerprint lock.
    locked = (task.metadata or {}).get("task_fingerprint_at_approval")
    if locked:
        current = fingerprint_task(task.to_dict())
        if current != locked:
            raise GateError(
                "Task scope changed after approval; reapproval required "
                f"(locked={locked[:12]}… current={current[:12]}…)"
            )

    locked_plan_fp = (task.metadata or {}).get("approved_plan_fingerprint")
    current_plan_fp = fingerprint_plan(plan.to_dict())
    if locked_plan_fp and locked_plan_fp != current_plan_fp:
        raise GateError("Approved plan fingerprint changed; reapproval required")
    if plan.approved_fingerprint and plan.approved_fingerprint != current_plan_fp:
        raise GateError("Plan content no longer matches approved fingerprint")

    try:
        inspection = inspect_repo(project_root)
    except GitSafetyError as exc:
        raise GateError(f"Git inspection failed: {exc}") from exc
    if not inspection.is_repo or not inspection.head:
        raise GateError("Project root is not a git repository with HEAD")
    if plan.starting_commit and inspection.head != plan.starting_commit:
        raise GateError(
            f"Starting commit mismatch: plan={plan.starting_commit} head={inspection.head}"
        )
    if require_clean_worktree and inspection.dirty:
        raise GateError("Clean-worktree requirement violated (working tree dirty)")


def assert_project_rules_compatible(
    registry: ProjectRegistry,
    task: Task,
) -> None:
    try:
        registry.require(task.project_id)
        for path in list(task.allowed_paths) + list(task.prohibited_paths):
            registry.ensure_path_allowed(task.project_id, path)
    except ProjectRegistryError as exc:
        raise GateError(f"Project rules incompatible: {exc}") from exc


def next_allowed_action(task: Task, plan: Plan | None) -> str:
    if task.status is TaskStatus.CANCELLED:
        return "none (cancelled)"
    if task.status is TaskStatus.BLOCKED:
        return "human review / unblock"
    if task.status is TaskStatus.DRAFT:
        return "set-task-status → ready_for_planning"
    if task.status is TaskStatus.READY_FOR_PLANNING:
        return "create-plan"
    if task.status is TaskStatus.PLANNED:
        if plan and plan.status is PlanStatus.READY_FOR_APPROVAL:
            return "approve-plan or reject-plan"
        if plan and plan.status is PlanStatus.DRAFT:
            return "submit-plan"
        return "submit-plan / validate-plan"
    if task.status is TaskStatus.APPROVED_FOR_IMPLEMENTATION:
        return "prepare-handoff --role cursor"
    if task.status is TaskStatus.IMPLEMENTING:
        return "record-report --kind implementation"
    if task.status is TaskStatus.VALIDATING:
        return "set-task-status → ready_for_review"
    if task.status is TaskStatus.READY_FOR_REVIEW:
        return "prepare-handoff --role codex / record-report --kind review"
    if task.status is TaskStatus.REVIEW_FAILED:
        return "record-repair-round / prepare-handoff --role cursor"
    if task.status is TaskStatus.REVIEW_PASSED:
        return "set-task-status → ready_to_commit"
    if task.status is TaskStatus.READY_TO_COMMIT:
        return "set-task-status → completed"
    if task.status is TaskStatus.COMPLETED:
        return "none (completed)"
    return "unknown"
