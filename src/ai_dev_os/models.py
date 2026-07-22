"""Core data models for AI Development OS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TaskType(str, Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    DOCS = "docs"
    REVIEW = "review"
    INDEPENDENT_REVIEW = "independent_review"
    UI = "ui"
    SMALL_FIX = "small_fix"
    VERIFICATION = "verification"
    ARCHITECTURE = "architecture"
    OTHER = "other"


class Complexity(str, Enum):
    SMALL = "small"
    NORMAL = "normal"
    COMPLEX = "complex"
    HIGH_RISK = "high_risk"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    DRAFT = "draft"
    READY_FOR_PLANNING = "ready_for_planning"
    PLANNED = "planned"
    APPROVED_FOR_IMPLEMENTATION = "approved_for_implementation"
    IMPLEMENTING = "implementing"
    VALIDATING = "validating"
    READY_FOR_REVIEW = "ready_for_review"
    REVIEW_FAILED = "review_failed"
    REVIEW_PASSED = "review_passed"
    READY_TO_COMMIT = "ready_to_commit"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ModelRole(str, Enum):
    CLAUDE = "claude"
    CURSOR = "cursor"
    CODEX = "codex"


class TokenUsageMode(str, Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class ReportOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


class ReviewVerdict(str, Enum):
    PASS = "pass"
    PASS_WITH_NOTES = "pass_with_notes"
    CHANGES_REQUIRED = "changes_required"
    BLOCKED = "blocked"


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NOTE = "note"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ApprovalRequirement(str, Enum):
    NONE = "none"
    HUMAN = "human"
    HUMAN_HIGH_RISK = "human_high_risk"


# Plan status transitions (superseded reachable from non-terminal active states).
PLAN_TRANSITIONS: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.DRAFT: frozenset(
        {PlanStatus.READY_FOR_APPROVAL, PlanStatus.SUPERSEDED, PlanStatus.REJECTED}
    ),
    PlanStatus.READY_FOR_APPROVAL: frozenset(
        {
            PlanStatus.APPROVED,
            PlanStatus.REJECTED,
            PlanStatus.DRAFT,
            PlanStatus.SUPERSEDED,
        }
    ),
    PlanStatus.APPROVED: frozenset({PlanStatus.SUPERSEDED, PlanStatus.DRAFT}),
    PlanStatus.REJECTED: frozenset({PlanStatus.SUPERSEDED, PlanStatus.DRAFT}),
    PlanStatus.SUPERSEDED: frozenset(),
}


# Allowed forward transitions. Special statuses blocked/cancelled reachable from most active states.
LIFECYCLE_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset(
        {TaskStatus.READY_FOR_PLANNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.READY_FOR_PLANNING: frozenset(
        {TaskStatus.PLANNED, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.PLANNED: frozenset(
        {
            TaskStatus.APPROVED_FOR_IMPLEMENTATION,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.APPROVED_FOR_IMPLEMENTATION: frozenset(
        {TaskStatus.IMPLEMENTING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.IMPLEMENTING: frozenset(
        {TaskStatus.VALIDATING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.VALIDATING: frozenset(
        {
            TaskStatus.READY_FOR_REVIEW,
            TaskStatus.IMPLEMENTING,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.READY_FOR_REVIEW: frozenset(
        {
            TaskStatus.REVIEW_PASSED,
            TaskStatus.REVIEW_FAILED,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.REVIEW_FAILED: frozenset(
        {
            TaskStatus.IMPLEMENTING,
            TaskStatus.READY_FOR_REVIEW,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.REVIEW_PASSED: frozenset(
        {TaskStatus.READY_TO_COMMIT, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.READY_TO_COMMIT: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.BLOCKED: frozenset(
        {
            TaskStatus.DRAFT,
            TaskStatus.READY_FOR_PLANNING,
            TaskStatus.PLANNED,
            TaskStatus.APPROVED_FOR_IMPLEMENTATION,
            TaskStatus.IMPLEMENTING,
            TaskStatus.VALIDATING,
            TaskStatus.READY_FOR_REVIEW,
            TaskStatus.REVIEW_FAILED,
            TaskStatus.REVIEW_PASSED,
            TaskStatus.READY_TO_COMMIT,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.CANCELLED: frozenset(),
}


@dataclass
class TokenUsage:
    mode: TokenUsageMode = TokenUsageMode.UNAVAILABLE
    input_tokens: int | None = None
    output_tokens: int | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TokenUsage:
        if not data:
            return cls()
        mode = TokenUsageMode(data.get("mode", TokenUsageMode.UNAVAILABLE.value))
        input_tokens = data.get("input_tokens")
        output_tokens = data.get("output_tokens")
        if mode is TokenUsageMode.UNAVAILABLE:
            # Never fabricate usage when unavailable.
            input_tokens = None
            output_tokens = None
        return cls(
            mode=mode,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            notes=data.get("notes"),
        )


@dataclass
class Task:
    id: str
    title: str
    description: str
    project_id: str
    task_type: TaskType
    complexity: Complexity
    risk_level: RiskLevel
    status: TaskStatus = TaskStatus.DRAFT
    acceptance_criteria: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    prohibited_paths: list[str] = field(default_factory=list)
    assigned_role: ModelRole | None = None
    routing_explanation: str | None = None
    token_budget_band: Complexity | None = None
    parent_task_id: str | None = None
    blocked_reason: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "project_id": self.project_id,
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "acceptance_criteria": list(self.acceptance_criteria),
            "allowed_paths": list(self.allowed_paths),
            "prohibited_paths": list(self.prohibited_paths),
            "assigned_role": self.assigned_role.value if self.assigned_role else None,
            "routing_explanation": self.routing_explanation,
            "token_budget_band": (
                self.token_budget_band.value if self.token_budget_band else None
            ),
            "parent_task_id": self.parent_task_id,
            "blocked_reason": self.blocked_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        assigned = data.get("assigned_role")
        budget = data.get("token_budget_band")
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            description=str(data["description"]),
            project_id=str(data["project_id"]),
            task_type=TaskType(data["task_type"]),
            complexity=Complexity(data["complexity"]),
            risk_level=RiskLevel(data["risk_level"]),
            status=TaskStatus(data.get("status", TaskStatus.DRAFT.value)),
            acceptance_criteria=list(data.get("acceptance_criteria") or []),
            allowed_paths=list(data.get("allowed_paths") or []),
            prohibited_paths=list(data.get("prohibited_paths") or []),
            assigned_role=ModelRole(assigned) if assigned else None,
            routing_explanation=data.get("routing_explanation"),
            token_budget_band=Complexity(budget) if budget else None,
            parent_task_id=data.get("parent_task_id"),
            blocked_reason=data.get("blocked_reason"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ProjectRecord:
    id: str
    name: str
    root_path: str
    description: str = ""
    default_branch: str = "main"
    allowed_path_prefixes: list[str] = field(default_factory=list)
    prohibited_path_prefixes: list[str] = field(default_factory=list)
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectRecord:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            root_path=str(data["root_path"]),
            description=str(data.get("description") or ""),
            default_branch=str(data.get("default_branch") or "main"),
            allowed_path_prefixes=list(data.get("allowed_path_prefixes") or []),
            prohibited_path_prefixes=list(data.get("prohibited_path_prefixes") or []),
            active=bool(data.get("active", True)),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class RoutingDecision:
    role: ModelRole
    explanation: str
    token_budget_band: Complexity

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "explanation": self.explanation,
            "token_budget_band": self.token_budget_band.value,
        }


@dataclass
class Plan:
    """Durable plan artifact (inspired by CC-SDD approved-spec + Liza audit fields)."""

    plan_id: str
    task_id: str
    project_id: str
    planner_agent: str
    starting_commit: str
    objective: str
    assumptions: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    files_expected_to_change: list[str] = field(default_factory=list)
    implementation_steps: list[str] = field(default_factory=list)
    testing_plan: list[str] = field(default_factory=list)
    rollback_or_recovery_plan: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    approval_requirement: ApprovalRequirement = ApprovalRequirement.HUMAN
    status: PlanStatus = PlanStatus.DRAFT
    created_timestamp: str = field(default_factory=utc_now_iso)
    approved_timestamp: str | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    content_fingerprint: str | None = None
    approved_fingerprint: str | None = None
    rejection_reason: str | None = None
    risk_level: RiskLevel = RiskLevel.MEDIUM

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "planner_agent": self.planner_agent,
            "starting_commit": self.starting_commit,
            "objective": self.objective,
            "assumptions": list(self.assumptions),
            "scope": list(self.scope),
            "prohibited_actions": list(self.prohibited_actions),
            "files_expected_to_change": list(self.files_expected_to_change),
            "implementation_steps": list(self.implementation_steps),
            "testing_plan": list(self.testing_plan),
            "rollback_or_recovery_plan": list(self.rollback_or_recovery_plan),
            "risks": list(self.risks),
            "unresolved_questions": list(self.unresolved_questions),
            "approval_requirement": self.approval_requirement.value,
            "status": self.status.value,
            "created_timestamp": self.created_timestamp,
            "approved_timestamp": self.approved_timestamp,
            "approved_by": self.approved_by,
            "approval_note": self.approval_note,
            "content_fingerprint": self.content_fingerprint,
            "approved_fingerprint": self.approved_fingerprint,
            "rejection_reason": self.rejection_reason,
            "risk_level": self.risk_level.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        return cls(
            plan_id=str(data["plan_id"]),
            task_id=str(data["task_id"]),
            project_id=str(data["project_id"]),
            planner_agent=str(data["planner_agent"]),
            starting_commit=str(data["starting_commit"]),
            objective=str(data["objective"]),
            assumptions=list(data.get("assumptions") or []),
            scope=list(data.get("scope") or []),
            prohibited_actions=list(data.get("prohibited_actions") or []),
            files_expected_to_change=list(data.get("files_expected_to_change") or []),
            implementation_steps=list(data.get("implementation_steps") or []),
            testing_plan=list(data.get("testing_plan") or []),
            rollback_or_recovery_plan=list(data.get("rollback_or_recovery_plan") or []),
            risks=list(data.get("risks") or []),
            unresolved_questions=list(data.get("unresolved_questions") or []),
            approval_requirement=ApprovalRequirement(
                data.get("approval_requirement", ApprovalRequirement.HUMAN.value)
            ),
            status=PlanStatus(data.get("status", PlanStatus.DRAFT.value)),
            created_timestamp=str(data.get("created_timestamp") or utc_now_iso()),
            approved_timestamp=data.get("approved_timestamp"),
            approved_by=data.get("approved_by"),
            approval_note=data.get("approval_note"),
            content_fingerprint=data.get("content_fingerprint"),
            approved_fingerprint=data.get("approved_fingerprint"),
            rejection_reason=data.get("rejection_reason"),
            risk_level=RiskLevel(data.get("risk_level", RiskLevel.MEDIUM.value)),
        )


@dataclass
class ImplementationReport:
    task_id: str
    summary: str
    files_changed: list[str]
    tests_run: list[str]
    outcome: ReportOutcome
    created_at: str = field(default_factory=utc_now_iso)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    notes: str | None = None
    plan_fingerprint: str | None = None
    task_fingerprint: str | None = None
    content_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "files_changed": list(self.files_changed),
            "tests_run": list(self.tests_run),
            "outcome": self.outcome.value,
            "created_at": self.created_at,
            "token_usage": self.token_usage.to_dict(),
            "notes": self.notes,
            "plan_fingerprint": self.plan_fingerprint,
            "task_fingerprint": self.task_fingerprint,
            "content_fingerprint": self.content_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImplementationReport:
        return cls(
            task_id=str(data["task_id"]),
            summary=str(data["summary"]),
            files_changed=list(data.get("files_changed") or []),
            tests_run=list(data.get("tests_run") or []),
            outcome=ReportOutcome(data["outcome"]),
            created_at=str(data.get("created_at") or utc_now_iso()),
            token_usage=TokenUsage.from_dict(data.get("token_usage")),
            notes=data.get("notes"),
            plan_fingerprint=data.get("plan_fingerprint"),
            task_fingerprint=data.get("task_fingerprint"),
            content_fingerprint=data.get("content_fingerprint"),
        )


@dataclass
class ReviewFinding:
    severity: FindingSeverity
    summary: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "summary": self.summary,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewFinding:
        return cls(
            severity=FindingSeverity(data["severity"]),
            summary=str(data["summary"]),
            path=data.get("path"),
        )


@dataclass
class ReviewReport:
    task_id: str
    reviewer_role: ModelRole
    verdict: ReviewVerdict
    findings: list[ReviewFinding] = field(default_factory=list)
    confirmed_findings: list[ReviewFinding] = field(default_factory=list)
    rejected_findings: list[ReviewFinding] = field(default_factory=list)
    notes: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    implementation_report_fingerprint: str | None = None
    content_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "reviewer_role": self.reviewer_role.value,
            "verdict": self.verdict.value,
            "findings": [f.to_dict() for f in self.findings],
            "confirmed_findings": [f.to_dict() for f in self.confirmed_findings],
            "rejected_findings": [f.to_dict() for f in self.rejected_findings],
            "notes": self.notes,
            "created_at": self.created_at,
            "implementation_report_fingerprint": self.implementation_report_fingerprint,
            "content_fingerprint": self.content_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewReport:
        def _findings(key: str) -> list[ReviewFinding]:
            return [ReviewFinding.from_dict(item) for item in (data.get(key) or [])]

        return cls(
            task_id=str(data["task_id"]),
            reviewer_role=ModelRole(data["reviewer_role"]),
            verdict=ReviewVerdict(data["verdict"]),
            findings=_findings("findings"),
            confirmed_findings=_findings("confirmed_findings"),
            rejected_findings=_findings("rejected_findings"),
            notes=data.get("notes"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            implementation_report_fingerprint=data.get(
                "implementation_report_fingerprint"
            ),
            content_fingerprint=data.get("content_fingerprint"),
        )


@dataclass
class RepairRound:
    """Repair iteration record (inspired by Ralphex max-round / stalemate concepts)."""

    task_id: str
    round_number: int
    reason: str
    findings_addressed: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    tests_rerun: list[str] = field(default_factory=list)
    result: str = "pending"
    scope_changed: bool = False
    reapproval_required: bool = False
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "round_number": self.round_number,
            "reason": self.reason,
            "findings_addressed": list(self.findings_addressed),
            "files_changed": list(self.files_changed),
            "tests_rerun": list(self.tests_rerun),
            "result": self.result,
            "scope_changed": self.scope_changed,
            "reapproval_required": self.reapproval_required,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepairRound:
        return cls(
            task_id=str(data["task_id"]),
            round_number=int(data["round_number"]),
            reason=str(data["reason"]),
            findings_addressed=list(data.get("findings_addressed") or []),
            files_changed=list(data.get("files_changed") or []),
            tests_rerun=list(data.get("tests_rerun") or []),
            result=str(data.get("result") or "pending"),
            scope_changed=bool(data.get("scope_changed", False)),
            reapproval_required=bool(data.get("reapproval_required", False)),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class BehavioralReport:
    generated_at: str
    task_count: int
    status_counts: dict[str, int]
    routing_counts: dict[str, int]
    recommendations: list[str]
    risk_counts: dict[str, int] = field(default_factory=dict)
    avg_complexity_band: str | None = None
    auto_rewrite_rules: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "task_count": self.task_count,
            "status_counts": dict(self.status_counts),
            "routing_counts": dict(self.routing_counts),
            "risk_counts": dict(self.risk_counts),
            "avg_complexity_band": self.avg_complexity_band,
            "recommendations": list(self.recommendations),
            "auto_rewrite_rules": False,
        }
