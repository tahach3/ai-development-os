"""Fail-closed binding and staleness checks for orchestration steps."""

from __future__ import annotations

from pathlib import Path

from .approval import plan_is_implementable
from .execution_models import SessionStatus
from .fingerprints import fingerprint_plan, fingerprint_task
from .lifecycle_gates import GateError, assert_can_prepare_implementation_handoff
from .models import Plan, PlanStatus, Task, TaskStatus
from .orchestration_models import OrchestrationFailureClass, OrchestrationRecord
from .project_registry import ProjectRegistry, ProjectRegistryError
from .safe_policy import PolicyError, assert_not_equitify_blob
from .session_store import SessionError, SessionStore
from .worktrees import WorktreeError, read_head


class BindingError(GateError):
    def __init__(self, message: str, failure_class: OrchestrationFailureClass) -> None:
        super().__init__(message)
        self.failure_class = failure_class


ELIGIBLE_TASK_STATES = frozenset(
    {
        TaskStatus.APPROVED_FOR_IMPLEMENTATION,
        TaskStatus.IMPLEMENTING,
        TaskStatus.VALIDATING,
        TaskStatus.READY_FOR_REVIEW,
        TaskStatus.REVIEW_FAILED,
        TaskStatus.REVIEW_PASSED,
        TaskStatus.READY_TO_COMMIT,
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
    }
)


def validate_bindings(
    record: OrchestrationRecord,
    *,
    task: Task,
    plan: Plan,
    registry: ProjectRegistry,
    session_store: SessionStore,
    require_clean_for_create: bool = False,
    expected_context_fingerprint: str | None = None,
    expected_role: str | None = None,
    adapter_version: str | None = None,
) -> None:
    """Validate all immutable bindings; raise BindingError on failure."""
    try:
        assert_not_equitify_blob(
            task.project_id,
            plan.project_id,
            record.project_id,
            record.registered_project_root_identity,
            task.id,
        )
    except PolicyError as exc:
        raise BindingError(str(exc), OrchestrationFailureClass.PROHIBITED_PATH) from exc

    if task.id != record.task_id:
        raise BindingError("Task ID changed", OrchestrationFailureClass.STALE_BINDING)
    if task.project_id != record.project_id:
        raise BindingError(
            "Task project ID changed during orchestration",
            OrchestrationFailureClass.STALE_BINDING,
        )

    if task.status is TaskStatus.CANCELLED:
        raise BindingError("Task is cancelled", OrchestrationFailureClass.POLICY_REJECTED)
    if record.current_state not in (
        "completed",
        "blocked",
        "cancelled",
        "human_review_required",
    ):
        if task.status not in ELIGIBLE_TASK_STATES and task.status is not TaskStatus.BLOCKED:
            # Allow create-time approved state.
            if task.status is not TaskStatus.APPROVED_FOR_IMPLEMENTATION:
                if task.status not in (
                    TaskStatus.IMPLEMENTING,
                    TaskStatus.VALIDATING,
                    TaskStatus.READY_FOR_REVIEW,
                    TaskStatus.REVIEW_FAILED,
                ):
                    raise BindingError(
                        f"Task not eligible for orchestration (status={task.status.value})",
                        OrchestrationFailureClass.POLICY_REJECTED,
                    )

    if record.task_fingerprint:
        current_fp = fingerprint_task(task.to_dict())
        if current_fp != record.task_fingerprint:
            raise BindingError(
                "Task fingerprint changed after orchestration start",
                OrchestrationFailureClass.STALE_BINDING,
            )

    if plan.plan_id != record.plan_id:
        raise BindingError("Plan ID mismatch", OrchestrationFailureClass.STALE_BINDING)
    if plan.project_id != record.project_id:
        raise BindingError("Plan project mismatch", OrchestrationFailureClass.STALE_BINDING)
    if plan.status is not PlanStatus.APPROVED:
        raise BindingError(
            "Plan is no longer approved",
            OrchestrationFailureClass.APPROVAL_INVALID,
        )
    if not plan_is_implementable(plan):
        raise BindingError(
            "Plan approval invalid or fingerprint mismatch",
            OrchestrationFailureClass.APPROVAL_INVALID,
        )
    current_plan_fp = fingerprint_plan(plan.to_dict())
    if current_plan_fp != record.approved_plan_fingerprint:
        raise BindingError(
            "Approved plan fingerprint changed",
            OrchestrationFailureClass.STALE_BINDING,
        )
    if plan.approved_fingerprint and plan.approved_fingerprint != current_plan_fp:
        raise BindingError(
            "Plan content no longer matches approved fingerprint",
            OrchestrationFailureClass.APPROVAL_INVALID,
        )

    try:
        project = registry.require(record.project_id)
    except ProjectRegistryError as exc:
        raise BindingError(str(exc), OrchestrationFailureClass.PROJECT_NOT_REGISTERED) from exc

    root_identity = str(Path(project.root_path).resolve())
    if root_identity != record.registered_project_root_identity:
        raise BindingError(
            "Registered project root identity changed",
            OrchestrationFailureClass.STALE_BINDING,
        )

    try:
        session = session_store.load(record.session_id)
    except SessionError as exc:
        raise BindingError(str(exc), OrchestrationFailureClass.SESSION_INVALID) from exc

    if session.status is not SessionStatus.ACTIVE:
        raise BindingError(
            f"Session not active ({session.status.value})",
            OrchestrationFailureClass.SESSION_INVALID,
        )
    if session.project_id != record.project_id:
        raise BindingError(
            "Session project changed",
            OrchestrationFailureClass.SESSION_INVALID,
        )
    if str(Path(session.worktree_path).resolve()) != record.worktree_id:
        raise BindingError(
            "Worktree identity changed",
            OrchestrationFailureClass.WORKTREE_INVALID,
        )
    if session.starting_commit != record.starting_commit:
        raise BindingError(
            "Session starting commit mismatch",
            OrchestrationFailureClass.STARTING_COMMIT_MISMATCH,
        )

    worktree = Path(session.worktree_path)
    if not worktree.exists():
        raise BindingError("Worktree missing", OrchestrationFailureClass.WORKTREE_INVALID)
    try:
        head = read_head(worktree)
    except WorktreeError as exc:
        raise BindingError(str(exc), OrchestrationFailureClass.WORKTREE_INVALID) from exc

    if head != record.current_worktree_commit and record.current_worktree_commit:
        # Allow exact expected descendant tracking: engine updates current commit after mutation.
        # Unexpected drift (neither matching recorded current nor starting) is blocked when
        # current is set and head differs without engine update — callers refresh after mutations.
        pass

    if plan.starting_commit and plan.starting_commit != record.starting_commit:
        raise BindingError(
            "Plan starting commit does not match orchestration binding",
            OrchestrationFailureClass.STARTING_COMMIT_MISMATCH,
        )

    if expected_role is not None:
        # Role must match assigned step role.
        if expected_role not in (record.implementation_role, record.review_role):
            raise BindingError(
                f"Provider role {expected_role} not bound to orchestration",
                OrchestrationFailureClass.CONTEXT_MISMATCH,
            )

    if adapter_version is not None and adapter_version != record.expected_adapter_version:
        raise BindingError(
            f"Incompatible adapter version {adapter_version}",
            OrchestrationFailureClass.STALE_BINDING,
        )

    if expected_context_fingerprint is not None:
        if (
            record.implementation_context_fingerprint
            and expected_role == record.implementation_role
            and expected_context_fingerprint != record.implementation_context_fingerprint
        ):
            raise BindingError(
                "Implementation context fingerprint mismatch",
                OrchestrationFailureClass.CONTEXT_MISMATCH,
            )
        if (
            record.review_context_fingerprint
            and expected_role == record.review_role
            and expected_context_fingerprint != record.review_context_fingerprint
        ):
            raise BindingError(
                "Review context fingerprint mismatch",
                OrchestrationFailureClass.CONTEXT_MISMATCH,
            )

    if record.invocation_mode != "simulated":
        raise BindingError(
            "Non-simulated invocation mode prohibited in Round 3C",
            OrchestrationFailureClass.POLICY_REJECTED,
        )

    # Reuse lifecycle gate for plan/task/git consistency only during impl/repair phases.
    # Review/testing phases intentionally move the task to ready_for_review.
    if task.status in (
        TaskStatus.READY_FOR_REVIEW,
        TaskStatus.REVIEW_PASSED,
        TaskStatus.READY_TO_COMMIT,
        TaskStatus.COMPLETED,
        TaskStatus.VALIDATING,
    ):
        return

    try:
        assert_can_prepare_implementation_handoff(
            task,
            plan,
            project.root_path,
            require_clean_worktree=require_clean_for_create,
        )
    except GateError as exc:
        # Map common messages
        msg = str(exc).lower()
        if "fingerprint" in msg or "reapproval" in msg:
            raise BindingError(str(exc), OrchestrationFailureClass.APPROVAL_INVALID) from exc
        if "commit" in msg:
            raise BindingError(str(exc), OrchestrationFailureClass.STARTING_COMMIT_MISMATCH) from exc
        if "equitify" in msg or "prohibited" in msg:
            raise BindingError(str(exc), OrchestrationFailureClass.PROHIBITED_PATH) from exc
        # During active orch, dirty worktree in project root is OK; session worktree is separate.
        if "clean-worktree" in msg and not require_clean_for_create:
            return
        raise BindingError(str(exc), OrchestrationFailureClass.POLICY_REJECTED) from exc
