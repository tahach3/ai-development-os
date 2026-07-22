"""Plan artifact persistence under workspace/plans."""

from __future__ import annotations

from pathlib import Path

import yaml

from .fingerprints import fingerprint_plan
from .models import Plan, PlanStatus, utc_now_iso
from .validation import ValidationError, validate_plan_dict, validate_plan_transition


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class PlanStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.plans_dir = base / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.yaml"

    def exists(self, plan_id: str) -> bool:
        return self._path(plan_id).exists()

    def save(self, plan: Plan) -> Path:
        plan.content_fingerprint = fingerprint_plan(plan.to_dict())
        validate_plan_dict(plan.to_dict())
        path = self._path(plan.plan_id)
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(plan.to_dict(), fh, sort_keys=False)
        return path

    def load(self, plan_id: str) -> Plan:
        path = self._path(plan_id)
        if not path.exists():
            raise ValidationError(f"Plan not found: {plan_id}")
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return validate_plan_dict(data)

    def list_plans(self, task_id: str | None = None) -> list[Plan]:
        plans: list[Plan] = []
        for path in sorted(self.plans_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            plan = validate_plan_dict(data)
            if task_id and plan.task_id != task_id:
                continue
            plans.append(plan)
        return plans

    def latest_for_task(self, task_id: str) -> Plan | None:
        plans = self.list_plans(task_id)
        if not plans:
            return None
        # Prefer non-superseded; otherwise latest by created_timestamp.
        active = [p for p in plans if p.status is not PlanStatus.SUPERSEDED]
        pool = active or plans
        return sorted(pool, key=lambda p: p.created_timestamp)[-1]

    def approved_for_task(self, task_id: str) -> Plan | None:
        for plan in self.list_plans(task_id):
            if plan.status is PlanStatus.APPROVED:
                return plan
        return None

    def create(self, data: dict) -> Plan:
        payload = dict(data)
        payload.setdefault("status", PlanStatus.DRAFT.value)
        payload.setdefault("created_timestamp", utc_now_iso())
        plan = validate_plan_dict(payload)
        plan.content_fingerprint = fingerprint_plan(plan.to_dict())
        if self.exists(plan.plan_id):
            raise ValidationError(f"Plan already exists: {plan.plan_id}")
        # Supersede prior non-terminal plans for the same task.
        for prior in self.list_plans(plan.task_id):
            if prior.status not in (PlanStatus.SUPERSEDED,):
                if prior.status is PlanStatus.APPROVED:
                    prior.status = PlanStatus.SUPERSEDED
                    self.save(prior)
                elif prior.status in (
                    PlanStatus.DRAFT,
                    PlanStatus.READY_FOR_APPROVAL,
                    PlanStatus.REJECTED,
                ):
                    prior.status = PlanStatus.SUPERSEDED
                    self.save(prior)
        self.save(plan)
        return plan

    def update(self, plan: Plan, *, invalidate_approval: bool = False) -> Plan:
        if not self.exists(plan.plan_id):
            raise ValidationError(f"Plan not found: {plan.plan_id}")
        current = self.load(plan.plan_id)
        new_fp = fingerprint_plan(plan.to_dict())
        old_fp = fingerprint_plan(current.to_dict())
        if (
            current.status is PlanStatus.APPROVED
            and new_fp != (current.approved_fingerprint or old_fp)
            and invalidate_approval
        ):
            plan.status = PlanStatus.DRAFT
            plan.approved_by = None
            plan.approved_timestamp = None
            plan.approved_fingerprint = None
            plan.approval_note = None
        plan.content_fingerprint = new_fp
        self.save(plan)
        return plan

    def transition(self, plan_id: str, new_status: PlanStatus) -> Plan:
        plan = self.load(plan_id)
        validate_plan_transition(plan.status, new_status)
        plan.status = new_status
        self.save(plan)
        return plan
