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
    FAIL = "fail"
    NEEDS_CHANGES = "needs_changes"


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NOTE = "note"


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
class ImplementationReport:
    task_id: str
    summary: str
    files_changed: list[str]
    tests_run: list[str]
    outcome: ReportOutcome
    created_at: str = field(default_factory=utc_now_iso)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    notes: str | None = None

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


@dataclass
class ReviewReport:
    task_id: str
    reviewer_role: ModelRole
    verdict: ReviewVerdict
    findings: list[ReviewFinding] = field(default_factory=list)
    notes: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "reviewer_role": self.reviewer_role.value,
            "verdict": self.verdict.value,
            "findings": [f.to_dict() for f in self.findings],
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewReport:
        findings = [
            ReviewFinding(
                severity=FindingSeverity(item["severity"]),
                summary=str(item["summary"]),
                path=item.get("path"),
            )
            for item in (data.get("findings") or [])
        ]
        return cls(
            task_id=str(data["task_id"]),
            reviewer_role=ModelRole(data["reviewer_role"]),
            verdict=ReviewVerdict(data["verdict"]),
            findings=findings,
            notes=data.get("notes"),
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
