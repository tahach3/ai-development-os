"""Round 3C orchestration models, enums, and schema constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .fingerprints import fingerprint
from .models import utc_now_iso


ORCHESTRATION_SCHEMA_VERSION = "3c.1"
ORCHESTRATION_POLICY_VERSION = "3c.1"
ORCHESTRATION_CONFIG_SCHEMA_VERSION = "3c.1"

AUTOMATION_ORCH_SIMULATED = "simulated_orchestration"


class OrchestrationState(str, Enum):
    CREATED = "created"
    READY = "ready"
    IMPLEMENTATION_PENDING = "implementation_pending"
    IMPLEMENTATION_RUNNING = "implementation_running"
    IMPLEMENTATION_RESULT_PENDING_VALIDATION = "implementation_result_pending_validation"
    TESTING_PENDING = "testing_pending"
    TESTING_RUNNING = "testing_running"
    REVIEW_PENDING = "review_pending"
    REVIEW_RUNNING = "review_running"
    REPAIR_REQUIRED = "repair_required"
    REPAIR_PENDING = "repair_pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


TERMINAL_ORCH_STATES = frozenset(
    {
        OrchestrationState.COMPLETED,
        OrchestrationState.BLOCKED,
        OrchestrationState.CANCELLED,
        OrchestrationState.HUMAN_REVIEW_REQUIRED,
    }
)


ORCH_TRANSITIONS: dict[OrchestrationState, frozenset[OrchestrationState]] = {
    OrchestrationState.CREATED: frozenset(
        {
            OrchestrationState.READY,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.READY: frozenset(
        {
            OrchestrationState.IMPLEMENTATION_PENDING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.IMPLEMENTATION_PENDING: frozenset(
        {
            OrchestrationState.IMPLEMENTATION_RUNNING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.IMPLEMENTATION_RUNNING: frozenset(
        {
            OrchestrationState.IMPLEMENTATION_RESULT_PENDING_VALIDATION,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.IMPLEMENTATION_RESULT_PENDING_VALIDATION: frozenset(
        {
            OrchestrationState.TESTING_PENDING,
            OrchestrationState.REPAIR_REQUIRED,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.TESTING_PENDING: frozenset(
        {
            OrchestrationState.TESTING_RUNNING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.TESTING_RUNNING: frozenset(
        {
            OrchestrationState.REVIEW_PENDING,
            OrchestrationState.REPAIR_REQUIRED,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.REVIEW_PENDING: frozenset(
        {
            OrchestrationState.REVIEW_RUNNING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.REVIEW_RUNNING: frozenset(
        {
            OrchestrationState.COMPLETED,
            OrchestrationState.REPAIR_REQUIRED,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.REPAIR_REQUIRED: frozenset(
        {
            OrchestrationState.REPAIR_PENDING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.REPAIR_PENDING: frozenset(
        {
            OrchestrationState.IMPLEMENTATION_PENDING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.HUMAN_REVIEW_REQUIRED,
        }
    ),
    OrchestrationState.COMPLETED: frozenset(),
    OrchestrationState.BLOCKED: frozenset(),
    OrchestrationState.CANCELLED: frozenset(),
    OrchestrationState.HUMAN_REVIEW_REQUIRED: frozenset(),
}


class OrchestrationFailureClass(str, Enum):
    NONE = "none"
    POLICY_REJECTED = "policy_rejected"
    STALE_BINDING = "stale_binding"
    APPROVAL_INVALID = "approval_invalid"
    PROJECT_NOT_REGISTERED = "project_not_registered"
    PROHIBITED_PATH = "prohibited_path"
    SESSION_INVALID = "session_invalid"
    WORKTREE_INVALID = "worktree_invalid"
    STARTING_COMMIT_MISMATCH = "starting_commit_mismatch"
    CONTEXT_MISMATCH = "context_mismatch"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_FAILED = "provider_failed"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_CANCELLED = "provider_cancelled"
    MALFORMED_PROVIDER_RESULT = "malformed_provider_result"
    DUPLICATE_REQUEST = "duplicate_request"
    IMPLEMENTATION_RESULT_INVALID = "implementation_result_invalid"
    TEST_COMMAND_REJECTED = "test_command_rejected"
    TESTS_FAILED = "tests_failed"
    REVIEW_RESULT_INVALID = "review_result_invalid"
    CHANGES_REQUIRED = "changes_required"
    REPAIR_LIMIT_REACHED = "repair_limit_reached"
    NO_PROGRESS = "no_progress"
    OSCILLATION_DETECTED = "oscillation_detected"
    STEP_LIMIT_REACHED = "step_limit_reached"
    SCOPE_CHANGE_DETECTED = "scope_change_detected"
    REAPPROVAL_REQUIRED = "reapproval_required"
    ORCHESTRATION_CANCELLED = "orchestration_cancelled"
    INTERNAL_PERSISTENCE_ERROR = "internal_persistence_error"
    STALEMATE = "stalemate"


class ProgressStatus(str, Enum):
    UNKNOWN = "unknown"
    PROGRESS = "progress"
    NO_PROGRESS = "no_progress"
    INDETERMINATE = "indeterminate"


class StalemateStatus(str, Enum):
    NONE = "none"
    DETECTED = "detected"
    CLEARED = "cleared"


class TestStatus(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass
class StructuredFinding:
    finding_id: str
    severity: str
    summary: str
    path: str | None = None
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "finding_id": self.finding_id,
            "path": self.path,
            "severity": self.severity,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StructuredFinding:
        return cls(
            finding_id=str(data.get("finding_id") or ""),
            severity=str(data.get("severity") or "note"),
            summary=str(data.get("summary") or ""),
            path=data.get("path"),
            code=data.get("code"),
        )

    def canonical_key(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "finding_id": self.finding_id,
            "path": self.path,
            "severity": self.severity,
            "summary": self.summary,
        }


def findings_fingerprint(findings: list[StructuredFinding]) -> str:
    payload = sorted((f.canonical_key() for f in findings), key=lambda x: canonical_json_key(x))
    return fingerprint(payload)


def canonical_json_key(item: dict[str, Any]) -> str:
    from .fingerprints import canonical_json

    return canonical_json(item)


@dataclass
class OrchestrationEvent:
    event_id: str
    orchestration_id: str
    from_state: str
    to_state: str
    step_number: int
    failure_class: str = OrchestrationFailureClass.NONE.value
    notes: str = ""
    refs: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "event_id": self.event_id,
            "failure_class": self.failure_class,
            "from_state": self.from_state,
            "notes": self.notes,
            "orchestration_id": self.orchestration_id,
            "refs": dict(sorted((self.refs or {}).items())),
            "step_number": self.step_number,
            "to_state": self.to_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationEvent:
        return cls(
            event_id=str(data["event_id"]),
            orchestration_id=str(data["orchestration_id"]),
            from_state=str(data["from_state"]),
            to_state=str(data["to_state"]),
            step_number=int(data.get("step_number") or 0),
            failure_class=str(data.get("failure_class") or OrchestrationFailureClass.NONE.value),
            notes=str(data.get("notes") or ""),
            refs=dict(data.get("refs") or {}),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass
class RoundEvidence:
    schema_version: str = ORCHESTRATION_SCHEMA_VERSION
    orchestration_id: str = ""
    round_number: int = 0
    repair_round_number: int = 0
    implementation_request_id: str | None = None
    implementation_result_id: str | None = None
    implementation_result_fingerprint: str | None = None
    implementation_context_fingerprint: str | None = None
    pre_implementation_commit: str | None = None
    post_implementation_commit: str | None = None
    worktree_diff_fingerprint: str | None = None
    files_changed: list[str] = field(default_factory=list)
    implementation_status: str = ""
    targeted_tests_requested: list[str] = field(default_factory=list)
    targeted_tests_executed: list[str] = field(default_factory=list)
    test_execution_result_id: str | None = None
    test_result_fingerprint: str | None = None
    passing_test_count: int | None = None
    failing_test_identifiers: list[str] = field(default_factory=list)
    failing_test_fingerprint: str | None = None
    review_request_id: str | None = None
    review_result_id: str | None = None
    review_result_fingerprint: str | None = None
    review_context_fingerprint: str | None = None
    review_verdict: str | None = None
    canonical_findings: list[StructuredFinding] = field(default_factory=list)
    review_findings_fingerprint: str | None = None
    findings_claimed_addressed: list[str] = field(default_factory=list)
    scope_change_indicator: bool = False
    reapproval_requirement: bool = False
    progress_evidence: dict[str, Any] = field(default_factory=dict)
    no_progress_reason: str | None = None
    stalemate_evidence: dict[str, Any] = field(default_factory=dict)
    round_result: str = ""
    started_at: str = ""
    finished_at: str = ""
    progress_state_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_findings": [f.to_dict() for f in self.canonical_findings],
            "failing_test_fingerprint": self.failing_test_fingerprint,
            "failing_test_identifiers": list(self.failing_test_identifiers),
            "files_changed": list(self.files_changed),
            "findings_claimed_addressed": list(self.findings_claimed_addressed),
            "finished_at": self.finished_at,
            "implementation_context_fingerprint": self.implementation_context_fingerprint,
            "implementation_request_id": self.implementation_request_id,
            "implementation_result_fingerprint": self.implementation_result_fingerprint,
            "implementation_result_id": self.implementation_result_id,
            "implementation_status": self.implementation_status,
            "no_progress_reason": self.no_progress_reason,
            "orchestration_id": self.orchestration_id,
            "passing_test_count": self.passing_test_count,
            "post_implementation_commit": self.post_implementation_commit,
            "pre_implementation_commit": self.pre_implementation_commit,
            "progress_evidence": dict(sorted((self.progress_evidence or {}).items())),
            "progress_state_fingerprint": self.progress_state_fingerprint,
            "reapproval_requirement": self.reapproval_requirement,
            "repair_round_number": self.repair_round_number,
            "review_context_fingerprint": self.review_context_fingerprint,
            "review_findings_fingerprint": self.review_findings_fingerprint,
            "review_request_id": self.review_request_id,
            "review_result_fingerprint": self.review_result_fingerprint,
            "review_result_id": self.review_result_id,
            "review_verdict": self.review_verdict,
            "round_number": self.round_number,
            "round_result": self.round_result,
            "schema_version": self.schema_version,
            "scope_change_indicator": self.scope_change_indicator,
            "stalemate_evidence": dict(sorted((self.stalemate_evidence or {}).items())),
            "started_at": self.started_at,
            "targeted_tests_executed": list(self.targeted_tests_executed),
            "targeted_tests_requested": list(self.targeted_tests_requested),
            "test_execution_result_id": self.test_execution_result_id,
            "test_result_fingerprint": self.test_result_fingerprint,
            "worktree_diff_fingerprint": self.worktree_diff_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoundEvidence:
        findings_raw = data.get("canonical_findings") or []
        return cls(
            schema_version=str(data.get("schema_version") or ORCHESTRATION_SCHEMA_VERSION),
            orchestration_id=str(data.get("orchestration_id") or ""),
            round_number=int(data.get("round_number") or 0),
            repair_round_number=int(data.get("repair_round_number") or 0),
            implementation_request_id=data.get("implementation_request_id"),
            implementation_result_id=data.get("implementation_result_id"),
            implementation_result_fingerprint=data.get("implementation_result_fingerprint"),
            implementation_context_fingerprint=data.get("implementation_context_fingerprint"),
            pre_implementation_commit=data.get("pre_implementation_commit"),
            post_implementation_commit=data.get("post_implementation_commit"),
            worktree_diff_fingerprint=data.get("worktree_diff_fingerprint"),
            files_changed=list(data.get("files_changed") or []),
            implementation_status=str(data.get("implementation_status") or ""),
            targeted_tests_requested=list(data.get("targeted_tests_requested") or []),
            targeted_tests_executed=list(data.get("targeted_tests_executed") or []),
            test_execution_result_id=data.get("test_execution_result_id"),
            test_result_fingerprint=data.get("test_result_fingerprint"),
            passing_test_count=data.get("passing_test_count"),
            failing_test_identifiers=list(data.get("failing_test_identifiers") or []),
            failing_test_fingerprint=data.get("failing_test_fingerprint"),
            review_request_id=data.get("review_request_id"),
            review_result_id=data.get("review_result_id"),
            review_result_fingerprint=data.get("review_result_fingerprint"),
            review_context_fingerprint=data.get("review_context_fingerprint"),
            review_verdict=data.get("review_verdict"),
            canonical_findings=[StructuredFinding.from_dict(x) for x in findings_raw],
            review_findings_fingerprint=data.get("review_findings_fingerprint"),
            findings_claimed_addressed=list(data.get("findings_claimed_addressed") or []),
            scope_change_indicator=bool(data.get("scope_change_indicator", False)),
            reapproval_requirement=bool(data.get("reapproval_requirement", False)),
            progress_evidence=dict(data.get("progress_evidence") or {}),
            no_progress_reason=data.get("no_progress_reason"),
            stalemate_evidence=dict(data.get("stalemate_evidence") or {}),
            round_result=str(data.get("round_result") or ""),
            started_at=str(data.get("started_at") or ""),
            finished_at=str(data.get("finished_at") or ""),
            progress_state_fingerprint=data.get("progress_state_fingerprint"),
        )


@dataclass
class OrchestrationRecord:
    schema_version: str = ORCHESTRATION_SCHEMA_VERSION
    orchestration_id: str = ""
    orchestration_policy_version: str = ORCHESTRATION_POLICY_VERSION
    task_id: str = ""
    task_fingerprint: str | None = None
    plan_id: str = ""
    approved_plan_fingerprint: str = ""
    approval_record_id: str | None = None
    project_id: str = ""
    session_id: str = ""
    worktree_id: str = ""
    registered_project_root_identity: str = ""
    starting_commit: str = ""
    current_worktree_commit: str = ""
    implementation_role: str = "cursor"
    review_role: str = "codex"
    implementation_provider_id: str = "simulated"
    review_provider_id: str = "simulated"
    implementation_adapter_version: str = "3b.1"
    review_adapter_version: str = "3b.1"
    invocation_mode: str = "simulated"
    implementation_context_fingerprint: str | None = None
    review_context_fingerprint: str | None = None
    current_state: str = OrchestrationState.CREATED.value
    current_step_number: int = 0
    maximum_step_count: int = 40
    current_repair_round: int = 0
    maximum_repair_rounds: int = 3
    transient_retry_count: int = 0
    review_verdict: str | None = None
    test_status: str = TestStatus.NOT_RUN.value
    progress_status: str = ProgressStatus.UNKNOWN.value
    stalemate_status: str = StalemateStatus.NONE.value
    stop_reason: str | None = None
    human_action_requirement: str | None = None
    created_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None
    cancelled_at: str | None = None
    latest_event_id: str | None = None
    automation_status: str = AUTOMATION_ORCH_SIMULATED
    scenario_id: str | None = None
    fixture_script: list[dict[str, Any]] = field(default_factory=list)
    fixture_index: int = 0
    consumed_request_ids: list[str] = field(default_factory=list)
    progress_fingerprint_history: list[str] = field(default_factory=list)
    consecutive_no_progress: int = 0
    consecutive_malformed: int = 0
    current_round_number: int = 0
    last_failure_class: str = OrchestrationFailureClass.NONE.value
    expected_adapter_version: str = "3b.1"
    test_paths: list[str] = field(default_factory=lambda: ["tests"])

    def state(self) -> OrchestrationState:
        return OrchestrationState(self.current_state)

    def is_terminal(self) -> bool:
        return self.state() in TERMINAL_ORCH_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_record_id": self.approval_record_id,
            "approved_plan_fingerprint": self.approved_plan_fingerprint,
            "automation_status": self.automation_status,
            "cancelled_at": self.cancelled_at,
            "completed_at": self.completed_at,
            "consecutive_malformed": self.consecutive_malformed,
            "consecutive_no_progress": self.consecutive_no_progress,
            "consumed_request_ids": list(self.consumed_request_ids),
            "created_at": self.created_at,
            "current_repair_round": self.current_repair_round,
            "current_round_number": self.current_round_number,
            "current_state": self.current_state,
            "current_step_number": self.current_step_number,
            "current_worktree_commit": self.current_worktree_commit,
            "expected_adapter_version": self.expected_adapter_version,
            "fixture_index": self.fixture_index,
            "fixture_script": list(self.fixture_script),
            "human_action_requirement": self.human_action_requirement,
            "implementation_adapter_version": self.implementation_adapter_version,
            "implementation_context_fingerprint": self.implementation_context_fingerprint,
            "implementation_provider_id": self.implementation_provider_id,
            "implementation_role": self.implementation_role,
            "invocation_mode": self.invocation_mode,
            "last_failure_class": self.last_failure_class,
            "latest_event_id": self.latest_event_id,
            "maximum_repair_rounds": self.maximum_repair_rounds,
            "maximum_step_count": self.maximum_step_count,
            "orchestration_id": self.orchestration_id,
            "orchestration_policy_version": self.orchestration_policy_version,
            "plan_id": self.plan_id,
            "progress_fingerprint_history": list(self.progress_fingerprint_history),
            "progress_status": self.progress_status,
            "project_id": self.project_id,
            "registered_project_root_identity": self.registered_project_root_identity,
            "review_adapter_version": self.review_adapter_version,
            "review_context_fingerprint": self.review_context_fingerprint,
            "review_provider_id": self.review_provider_id,
            "review_role": self.review_role,
            "review_verdict": self.review_verdict,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "stalemate_status": self.stalemate_status,
            "starting_commit": self.starting_commit,
            "stop_reason": self.stop_reason,
            "task_fingerprint": self.task_fingerprint,
            "task_id": self.task_id,
            "test_paths": list(self.test_paths),
            "test_status": self.test_status,
            "transient_retry_count": self.transient_retry_count,
            "updated_at": self.updated_at,
            "worktree_id": self.worktree_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationRecord:
        schema = str(data.get("schema_version") or "")
        if schema and schema != ORCHESTRATION_SCHEMA_VERSION:
            raise ValueError(f"Unsupported orchestration schema version: {schema}")
        return cls(
            schema_version=schema or ORCHESTRATION_SCHEMA_VERSION,
            orchestration_id=str(data.get("orchestration_id") or ""),
            orchestration_policy_version=str(
                data.get("orchestration_policy_version") or ORCHESTRATION_POLICY_VERSION
            ),
            task_id=str(data.get("task_id") or ""),
            task_fingerprint=data.get("task_fingerprint"),
            plan_id=str(data.get("plan_id") or ""),
            approved_plan_fingerprint=str(data.get("approved_plan_fingerprint") or ""),
            approval_record_id=data.get("approval_record_id"),
            project_id=str(data.get("project_id") or ""),
            session_id=str(data.get("session_id") or ""),
            worktree_id=str(data.get("worktree_id") or ""),
            registered_project_root_identity=str(
                data.get("registered_project_root_identity") or ""
            ),
            starting_commit=str(data.get("starting_commit") or ""),
            current_worktree_commit=str(data.get("current_worktree_commit") or ""),
            implementation_role=str(data.get("implementation_role") or "cursor"),
            review_role=str(data.get("review_role") or "codex"),
            implementation_provider_id=str(
                data.get("implementation_provider_id") or "simulated"
            ),
            review_provider_id=str(data.get("review_provider_id") or "simulated"),
            implementation_adapter_version=str(
                data.get("implementation_adapter_version") or "3b.1"
            ),
            review_adapter_version=str(data.get("review_adapter_version") or "3b.1"),
            invocation_mode=str(data.get("invocation_mode") or "simulated"),
            implementation_context_fingerprint=data.get("implementation_context_fingerprint"),
            review_context_fingerprint=data.get("review_context_fingerprint"),
            current_state=str(data.get("current_state") or OrchestrationState.CREATED.value),
            current_step_number=int(data.get("current_step_number") or 0),
            maximum_step_count=int(data.get("maximum_step_count") or 40),
            current_repair_round=int(data.get("current_repair_round") or 0),
            maximum_repair_rounds=int(data.get("maximum_repair_rounds") or 3),
            transient_retry_count=int(data.get("transient_retry_count") or 0),
            review_verdict=data.get("review_verdict"),
            test_status=str(data.get("test_status") or TestStatus.NOT_RUN.value),
            progress_status=str(data.get("progress_status") or ProgressStatus.UNKNOWN.value),
            stalemate_status=str(data.get("stalemate_status") or StalemateStatus.NONE.value),
            stop_reason=data.get("stop_reason"),
            human_action_requirement=data.get("human_action_requirement"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            completed_at=data.get("completed_at"),
            cancelled_at=data.get("cancelled_at"),
            latest_event_id=data.get("latest_event_id"),
            automation_status=str(
                data.get("automation_status") or AUTOMATION_ORCH_SIMULATED
            ),
            scenario_id=data.get("scenario_id"),
            fixture_script=list(data.get("fixture_script") or []),
            fixture_index=int(data.get("fixture_index") or 0),
            consumed_request_ids=list(data.get("consumed_request_ids") or []),
            progress_fingerprint_history=list(data.get("progress_fingerprint_history") or []),
            consecutive_no_progress=int(data.get("consecutive_no_progress") or 0),
            consecutive_malformed=int(data.get("consecutive_malformed") or 0),
            current_round_number=int(data.get("current_round_number") or 0),
            last_failure_class=str(
                data.get("last_failure_class") or OrchestrationFailureClass.NONE.value
            ),
            expected_adapter_version=str(data.get("expected_adapter_version") or "3b.1"),
            test_paths=list(data.get("test_paths") or ["tests"]),
        )


@dataclass
class CompletionSummary:
    schema_version: str = ORCHESTRATION_SCHEMA_VERSION
    orchestration_id: str = ""
    final_state: str = ""
    repair_rounds_used: int = 0
    steps_used: int = 0
    review_verdict: str | None = None
    test_status: str | None = None
    stalemate_status: str | None = None
    stop_reason: str | None = None
    progress_status: str | None = None
    human_action_requirement: str | None = None
    automation_status: str = AUTOMATION_ORCH_SIMULATED
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "automation_status": self.automation_status,
            "created_at": self.created_at or utc_now_iso(),
            "final_state": self.final_state,
            "human_action_requirement": self.human_action_requirement,
            "orchestration_id": self.orchestration_id,
            "progress_status": self.progress_status,
            "repair_rounds_used": self.repair_rounds_used,
            "review_verdict": self.review_verdict,
            "schema_version": self.schema_version,
            "stalemate_status": self.stalemate_status,
            "steps_used": self.steps_used,
            "stop_reason": self.stop_reason,
            "test_status": self.test_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompletionSummary:
        return cls(
            schema_version=str(data.get("schema_version") or ORCHESTRATION_SCHEMA_VERSION),
            orchestration_id=str(data.get("orchestration_id") or ""),
            final_state=str(data.get("final_state") or ""),
            repair_rounds_used=int(data.get("repair_rounds_used") or 0),
            steps_used=int(data.get("steps_used") or 0),
            review_verdict=data.get("review_verdict"),
            test_status=data.get("test_status"),
            stalemate_status=data.get("stalemate_status"),
            stop_reason=data.get("stop_reason"),
            progress_status=data.get("progress_status"),
            human_action_requirement=data.get("human_action_requirement"),
            automation_status=str(
                data.get("automation_status") or AUTOMATION_ORCH_SIMULATED
            ),
            created_at=str(data.get("created_at") or ""),
        )


def next_allowed_orch_action(state: OrchestrationState) -> str:
    if state is OrchestrationState.CREATED:
        return "validate-orchestration"
    if state is OrchestrationState.READY:
        return "orchestration-step (begin implementation)"
    if state is OrchestrationState.IMPLEMENTATION_PENDING:
        return "orchestration-step (run implementation)"
    if state is OrchestrationState.IMPLEMENTATION_RUNNING:
        return "orchestration-step (finish implementation)"
    if state is OrchestrationState.IMPLEMENTATION_RESULT_PENDING_VALIDATION:
        return "orchestration-step (validate implementation result)"
    if state is OrchestrationState.TESTING_PENDING:
        return "orchestration-step (run targeted tests)"
    if state is OrchestrationState.TESTING_RUNNING:
        return "orchestration-step (finish tests)"
    if state is OrchestrationState.REVIEW_PENDING:
        return "orchestration-step (run review)"
    if state is OrchestrationState.REVIEW_RUNNING:
        return "orchestration-step (finish review)"
    if state is OrchestrationState.REPAIR_REQUIRED:
        return "orchestration-step (open repair) or cancel"
    if state is OrchestrationState.REPAIR_PENDING:
        return "orchestration-step (begin repair implementation)"
    if state is OrchestrationState.COMPLETED:
        return "none (completed)"
    if state is OrchestrationState.BLOCKED:
        return "human review / new orchestration"
    if state is OrchestrationState.CANCELLED:
        return "none (cancelled; create new orchestration)"
    if state is OrchestrationState.HUMAN_REVIEW_REQUIRED:
        return "human review (stalemate or escalation)"
    return "unknown"
