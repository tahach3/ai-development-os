"""Plan approval gate — human approval with fingerprint locking."""

from __future__ import annotations

from pathlib import Path

from .constitutional_court import CourtEvidenceEnvelope, is_major_change
from .court_store import CourtStore
from .fingerprints import fingerprint_plan, fingerprint_task
from .models import Plan, PlanStatus, RiskLevel, TaskStatus, utc_now_iso
from .plan_store import PlanStore
from .task_store import TaskStore
from .validation import ValidationError, apply_status_transition, validate_plan_transition


HIGH_RISK_LEVELS = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})


def refresh_content_fingerprint(plan: Plan) -> str:
    fp = fingerprint_plan(plan.to_dict())
    plan.content_fingerprint = fp
    return fp


def submit_plan(store: PlanStore, plan_id: str) -> Plan:
    plan = store.load(plan_id)
    validate_plan_transition(plan.status, PlanStatus.READY_FOR_APPROVAL)
    refresh_content_fingerprint(plan)
    plan.status = PlanStatus.READY_FOR_APPROVAL
    store.save(plan)
    return plan


def approve_plan(
    plan_store: PlanStore,
    task_store: TaskStore,
    plan_id: str,
    *,
    approver: str,
    note: str | None = None,
    court_store: CourtStore | None = None,
    workspace_root: Path | None = None,
) -> Plan:
    plan = plan_store.load(plan_id)
    if plan.status is not PlanStatus.READY_FOR_APPROVAL:
        raise ValidationError(
            f"Plan must be ready_for_approval to approve (got {plan.status.value})"
        )
    if not approver or not str(approver).strip():
        raise ValidationError("Approver is required")
    approver_norm = str(approver).strip()
    planner_norm = str(plan.planner_agent).strip()
    if plan.risk_level in HIGH_RISK_LEVELS and approver_norm.lower() == planner_norm.lower():
        raise ValidationError(
            "Self-approval rejected: high/critical-risk plans cannot be approved "
            "by the same agent that planned them"
        )

    task = task_store.load(plan.task_id)
    if task.status in (TaskStatus.BLOCKED, TaskStatus.CANCELLED):
        raise ValidationError(f"Cannot approve plan for {task.status.value} task")
    if task.status is not TaskStatus.PLANNED:
        raise ValidationError(
            f"Task must be planned before plan approval (got {task.status.value})"
        )

    # §5.2: major changes require an additional fresh matching Court pass artifact.
    # Low/medium non-major plans are unaffected (no court metadata locked).
    court_meta: dict[str, str] | None = None
    if is_major_change(task, plan, CourtEvidenceEnvelope()):
        store = court_store or CourtStore(workspace_root)
        plan_fp = fingerprint_plan(plan.to_dict())
        record = store.latest_passing_for_plan(plan.plan_id, plan_fp)
        if record is None:
            raise ValidationError(
                "Constitutional Court required: major change needs a fresh matching "
                "Court pass/pass_with_notes record (same plan fingerprint) before "
                "approve-plan; run constitutional-check then retry"
            )
        court_meta = {
            "court_record_id": record.record_id,
            "court_content_fingerprint": record.content_fingerprint,
        }

    fp = refresh_content_fingerprint(plan)
    plan.status = PlanStatus.APPROVED
    plan.approved_by = approver_norm
    plan.approved_timestamp = utc_now_iso()
    plan.approval_note = note
    plan.approved_fingerprint = fp
    plan_store.save(plan)

    # Lock task scope fingerprint at approval time.
    task = apply_status_transition(task, TaskStatus.APPROVED_FOR_IMPLEMENTATION)
    meta = dict(task.metadata)
    meta["approved_plan_id"] = plan.plan_id
    meta["approved_plan_fingerprint"] = fp
    meta["task_fingerprint_at_approval"] = fingerprint_task(task.to_dict())
    meta["starting_commit_at_approval"] = plan.starting_commit
    if court_meta:
        meta.update(court_meta)
    task.metadata = meta
    task_store.update(task)
    return plan


def reject_plan(
    plan_store: PlanStore,
    plan_id: str,
    *,
    rejected_by: str,
    reason: str,
) -> Plan:
    plan = plan_store.load(plan_id)
    if plan.status not in (PlanStatus.READY_FOR_APPROVAL, PlanStatus.DRAFT):
        raise ValidationError(
            f"Plan cannot be rejected from status {plan.status.value}"
        )
    validate_plan_transition(plan.status, PlanStatus.REJECTED)
    plan.status = PlanStatus.REJECTED
    plan.rejection_reason = reason
    plan.approved_by = None
    plan.approved_timestamp = None
    plan.approved_fingerprint = None
    plan.approval_note = f"rejected_by={rejected_by}"
    plan_store.save(plan)
    return plan


def apply_plan_content_update(plan_store: PlanStore, plan: Plan) -> Plan:
    """Save plan; invalidate approval if implementation-relevant content changed."""
    current = plan_store.load(plan.plan_id)
    new_fp = fingerprint_plan(plan.to_dict())
    old_approved = current.approved_fingerprint
    was_approved = current.status is PlanStatus.APPROVED
    if was_approved and old_approved and new_fp != old_approved:
        plan.status = PlanStatus.DRAFT
        plan.approved_by = None
        plan.approved_timestamp = None
        plan.approved_fingerprint = None
        plan.approval_note = None
        plan.rejection_reason = None
    plan.content_fingerprint = new_fp
    plan_store.save(plan)
    return plan


def plan_is_implementable(plan: Plan) -> bool:
    if plan.status is not PlanStatus.APPROVED:
        return False
    current = fingerprint_plan(plan.to_dict())
    return bool(plan.approved_fingerprint) and current == plan.approved_fingerprint
