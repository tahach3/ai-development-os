"""Provider execution policy gates and binding validation (Round 3B)."""

from __future__ import annotations

from pathlib import Path

from .execution_models import SessionStatus
from .fingerprints import fingerprint_plan
from .models import ModelRole, PlanStatus, RiskLevel, Task, TaskStatus
from .plan_store import PlanStore
from .project_registry import ProjectRegistry, ProjectRegistryError
from .provider_config import ProviderConfig
from .provider_models import (
    FailureClass,
    ProviderMode,
    ProviderRequest,
)
from .safe_policy import PolicyError, assert_not_equitify_blob
from .session_store import SessionStore
from .task_store import TaskStore


HIGH_RISK = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})

# Modes that may execute simulated fixtures (not live model calls).
EXECUTABLE_MODES = frozenset(
    {
        ProviderMode.SIMULATED,
        ProviderMode.DISCOVERY_ONLY,
        ProviderMode.MANUAL_HANDOFF,
        ProviderMode.LIVE_LOCAL_CLI_ALLOWED,
    }
)


class ProviderPolicyError(PolicyError):
    """Provider gate / binding failure."""

    def __init__(self, message: str, failure_class: FailureClass = FailureClass.POLICY_REJECTED):
        super().__init__(message)
        self.failure_class = failure_class


def project_allows_provider(project_metadata: dict, provider_id: str) -> bool:
    allowed = project_metadata.get("allowed_providers")
    if allowed is None:
        return False
    if not isinstance(allowed, list):
        return False
    return provider_id in {str(x) for x in allowed}


def task_has_provider_execution_approval(task: Task) -> bool:
    meta = task.metadata or {}
    return bool(meta.get("provider_execution_approved"))


def task_allows_high_risk_live(task: Task) -> bool:
    meta = task.metadata or {}
    return bool(meta.get("allow_high_risk_live"))


def assert_request_bindings(
    request: ProviderRequest,
    *,
    task_store: TaskStore,
    plan_store: PlanStore,
    session_store: SessionStore,
    registry: ProjectRegistry,
    expect_mode: ProviderMode | None = None,
) -> tuple[Task, object, object]:
    """Reload entities and reject on mismatch. Returns (task, plan, session)."""
    assert_not_equitify_blob(
        request.project_id,
        request.task_id,
        request.session_id,
        request.worktree_id,
        request.provider_id,
    )

    try:
        project = registry.require(request.project_id)
    except ProjectRegistryError as exc:
        raise ProviderPolicyError(str(exc)) from exc

    assert_not_equitify_blob(project.id, project.name, project.root_path)

    task = task_store.load(request.task_id)
    if task.project_id != request.project_id:
        raise ProviderPolicyError(
            "Provider request cannot change its project",
            FailureClass.STALE_BINDING,
        )

    try:
        role = ModelRole(request.role)
    except ValueError as exc:
        raise ProviderPolicyError(f"Invalid role: {request.role}") from exc

    assigned = task.assigned_role
    if assigned and assigned is not role:
        # Independent review may use a distinct reviewer role (Round 3C).
        independent_review_ok = role is ModelRole.CODEX and task.status in (
            TaskStatus.READY_FOR_REVIEW,
            TaskStatus.REVIEW_FAILED,
            TaskStatus.REVIEW_PASSED,
            TaskStatus.IMPLEMENTING,
            TaskStatus.VALIDATING,
            TaskStatus.APPROVED_FOR_IMPLEMENTATION,
        )
        if not independent_review_ok:
            raise ProviderPolicyError(
                "Provider request cannot change its role",
                FailureClass.STALE_BINDING,
            )

    plan = plan_store.load(request.plan_id)
    if plan.task_id != request.task_id or plan.project_id != request.project_id:
        raise ProviderPolicyError(
            "Plan binding mismatch for provider request",
            FailureClass.STALE_BINDING,
        )

    session = session_store.load(request.session_id)
    if session.project_id != request.project_id:
        raise ProviderPolicyError(
            "Provider request cannot change its session project",
            FailureClass.STALE_BINDING,
        )
    if session.status not in (SessionStatus.CREATED, SessionStatus.ACTIVE):
        raise ProviderPolicyError(
            f"Session not active for provider execution (status={session.status.value})"
        )
    worktree = str(Path(session.worktree_path).resolve())
    if Path(request.worktree_id).resolve() != Path(worktree).resolve() and request.worktree_id != session.session_id:
        # worktree_id may be session id or absolute worktree path
        if request.worktree_id not in (session.session_id, session.worktree_path, worktree):
            raise ProviderPolicyError(
                "Provider request cannot change its session or worktree",
                FailureClass.STALE_BINDING,
            )

    if request.starting_commit != session.starting_commit:
        raise ProviderPolicyError(
            "Stale starting commit binding",
            FailureClass.STALE_BINDING,
        )

    current_fp = fingerprint_plan(plan.to_dict())
    if plan.status is PlanStatus.APPROVED:
        locked = plan.approved_fingerprint or current_fp
        if request.approved_plan_fingerprint != locked:
            raise ProviderPolicyError(
                "Stale plan fingerprint binding",
                FailureClass.STALE_BINDING,
            )
        if current_fp != locked:
            raise ProviderPolicyError(
                "Plan content no longer matches approved fingerprint",
                FailureClass.STALE_BINDING,
            )

    ctx_meta = (task.metadata or {}).get("context_or_handoff_fingerprint")
    if ctx_meta and ctx_meta != request.context_or_handoff_fingerprint:
        raise ProviderPolicyError(
            "Stale context/handoff fingerprint binding",
            FailureClass.STALE_BINDING,
        )

    if expect_mode is not None and request.invocation_mode is not expect_mode:
        raise ProviderPolicyError(
            f"Invocation mode mismatch: request={request.invocation_mode.value} "
            f"expected={expect_mode.value}"
        )

    return task, plan, session


def assert_may_run_provider(
    request: ProviderRequest,
    *,
    config: ProviderConfig,
    task_store: TaskStore,
    plan_store: PlanStore,
    session_store: SessionStore,
    registry: ProjectRegistry,
    require_live_gates: bool = False,
) -> tuple[Task, object, object]:
    """Full gate check before simulated or live execution."""
    effective = config.effective_mode(request.provider_id)
    if effective is ProviderMode.DISABLED:
        raise ProviderPolicyError("Provider is disabled")

    if request.invocation_mode is ProviderMode.DISABLED:
        raise ProviderPolicyError("Request invocation_mode is disabled")

    if request.invocation_mode is ProviderMode.LIVE_LOCAL_CLI_ALLOWED or require_live_gates:
        return assert_live_gates(
            request,
            config=config,
            task_store=task_store,
            plan_store=plan_store,
            session_store=session_store,
            registry=registry,
        )

    if request.invocation_mode is ProviderMode.SIMULATED:
        if effective is not ProviderMode.SIMULATED:
            raise ProviderPolicyError(
                f"Provider mode {effective.value} does not allow simulated execution"
            )

    task, plan, session = assert_request_bindings(
        request,
        task_store=task_store,
        plan_store=plan_store,
        session_store=session_store,
        registry=registry,
    )

    if request.invocation_mode is ProviderMode.SIMULATED:
        # Simulated still requires registered project + active session bindings.
        # Unapproved plans may not invoke implementation providers (even simulated)
        # when role is an implementation role — gate on plan approval for impl roles.
        if request.role in (ModelRole.CLAUDE.value, ModelRole.CURSOR.value):
            if plan.status is not PlanStatus.APPROVED:
                raise ProviderPolicyError(
                    "Unapproved plans cannot invoke implementation providers"
                )
            if task.status not in (
                TaskStatus.APPROVED_FOR_IMPLEMENTATION,
                TaskStatus.IMPLEMENTING,
                TaskStatus.VALIDATING,
                TaskStatus.READY_FOR_REVIEW,
                TaskStatus.REVIEW_FAILED,
            ):
                # Allow approved_for_implementation and onward for sim impl.
                if task.status is not TaskStatus.APPROVED_FOR_IMPLEMENTATION:
                    if task.status not in (
                        TaskStatus.IMPLEMENTING,
                        TaskStatus.VALIDATING,
                        TaskStatus.READY_FOR_REVIEW,
                        TaskStatus.REVIEW_FAILED,
                        TaskStatus.REVIEW_PASSED,
                    ):
                        raise ProviderPolicyError(
                            f"Task status {task.status.value} not eligible for provider simulation"
                        )

    return task, plan, session


def assert_live_gates(
    request: ProviderRequest,
    *,
    config: ProviderConfig,
    task_store: TaskStore,
    plan_store: PlanStore,
    session_store: SessionStore,
    registry: ProjectRegistry,
) -> tuple[Task, object, object]:
    entry = config.get_entry(request.provider_id)
    effective = config.effective_mode(request.provider_id)
    if effective is not ProviderMode.LIVE_LOCAL_CLI_ALLOWED or not entry.allow_live:
        raise ProviderPolicyError(
            "Live mode cannot be entered without explicit provider permission"
        )

    task, plan, session = assert_request_bindings(
        request,
        task_store=task_store,
        plan_store=plan_store,
        session_store=session_store,
        registry=registry,
    )

    project = registry.require(request.project_id)
    if not project_allows_provider(project.metadata or {}, request.provider_id):
        raise ProviderPolicyError(
            "Live mode cannot be entered without explicit project permission"
        )

    if plan.status is not PlanStatus.APPROVED:
        raise ProviderPolicyError("Unapproved plans cannot invoke implementation providers")

    if not task_has_provider_execution_approval(task):
        raise ProviderPolicyError(
            "Live mode cannot be entered without explicit task-level execution approval"
        )

    if task.risk_level in HIGH_RISK and not task_allows_high_risk_live(task):
        raise ProviderPolicyError(
            "High-risk/critical work is not auto-executable merely because a provider is enabled"
        )

    if request.role in (ModelRole.CLAUDE.value, ModelRole.CURSOR.value):
        if task.status not in (
            TaskStatus.APPROVED_FOR_IMPLEMENTATION,
            TaskStatus.IMPLEMENTING,
        ):
            raise ProviderPolicyError(
                f"Task status {task.status.value} not eligible for live implementation provider"
            )

    # Worktree path must exist
    wt = Path(session.worktree_path)
    if not wt.exists():
        raise ProviderPolicyError("Session worktree is not valid")

    assert_not_equitify_blob(str(wt), *(task.prohibited_paths or []))

    raise ProviderPolicyError(
        "Live provider model execution is not authorized in Round 3B validation; "
        "requires separately authorized live smoke test"
    )
