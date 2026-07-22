"""Round 3B provider-neutral contracts, envelopes, and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .fingerprints import fingerprint
from .models import utc_now_iso


PROVIDER_RESULT_SCHEMA_VERSION = "3b.1"
PROVIDER_ADAPTER_VERSION = "3b.1"
PROVIDER_CONFIG_SCHEMA_VERSION = "3b.1"

AUTOMATION_MANUAL = "manual_handoff"
AUTOMATION_DISCOVERY = "discovery_only"
AUTOMATION_SIMULATED = "simulated_provider_execution"
AUTOMATION_LIVE = "live_local_cli"
AUTOMATION_DISABLED = "disabled"


class ProviderId(str, Enum):
    SIMULATED = "simulated"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"


class ProviderMode(str, Enum):
    DISABLED = "disabled"
    DISCOVERY_ONLY = "discovery_only"
    SIMULATED = "simulated"
    MANUAL_HANDOFF = "manual_handoff"
    LIVE_LOCAL_CLI_ALLOWED = "live_local_cli_allowed"


class InstallationStatus(str, Enum):
    NOT_INSTALLED = "not_installed"
    DETECTED = "detected"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


class AvailabilityStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    DISCOVERY_READY = "discovery_ready"
    SIMULATION_READY = "simulation_ready"
    MANUAL_ONLY = "manual_only"
    LIVE_GATED = "live_gated"
    DISABLED = "disabled"


class AuthCategory(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    ASSUMED_EXTERNAL_CLI_SESSION = "assumed_external_cli_session"


class NetworkUse(str, Enum):
    NONE_EXPECTED = "none_expected"
    MAY_CONTACT_PROVIDER_BACKEND = "may_contact_provider_backend"
    UNKNOWN = "unknown"


class ProviderResultStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"
    DUPLICATE = "duplicate"


class FailureClass(str, Enum):
    NONE = "none"
    POLICY_REJECTED = "policy_rejected"
    NOT_INSTALLED = "not_installed"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    NONZERO_EXIT = "nonzero_exit"
    MALFORMED_OUTPUT = "malformed_output"
    MISSING_ARTIFACT = "missing_artifact"
    DUPLICATE_REQUEST = "duplicate_request"
    STALE_BINDING = "stale_binding"
    PROVIDER_ERROR = "provider_error"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class SimulatedFixture(str, Enum):
    SUCCESS_IMPL = "success_impl"
    SUCCESS_REVIEW = "success_review"
    SUCCESS_REVIEW_WITH_NOTES = "success_review_with_notes"
    CHANGES_REQUIRED_REVIEW = "changes_required_review"
    CHANGES_REQUIRED_IDENTICAL = "changes_required_identical"
    MALFORMED_REVIEW = "malformed_review"
    PROVIDER_REJECTION = "provider_rejection"
    MALFORMED_OUTPUT = "malformed_output"
    TIMEOUT = "timeout"
    NONZERO_EXIT = "nonzero_exit"
    TRUNCATED_OUTPUT = "truncated_output"
    MISSING_ARTIFACT = "missing_artifact"
    DUPLICATE_REQUEST = "duplicate_request"
    STALE_PLAN = "stale_plan"
    STALE_COMMIT = "stale_commit"
    STALE_CONTEXT = "stale_context"
    CANCELLED = "cancelled"
    SCOPE_CHANGE = "scope_change"


@dataclass
class ProviderCapability:
    provider_id: str
    adapter_version: str
    executable_identity: str
    detected_version: str | None
    installation_status: InstallationStatus
    availability_status: AvailabilityStatus
    supported_roles: list[str]
    supported_modes: list[str]
    supports_noninteractive: bool
    supports_stdin_prompt: bool
    supports_file_prompt: bool
    auth_category: AuthCategory
    network_use: NetworkUse
    live_execution_permission: bool
    automation_status: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "auth_category": self.auth_category.value,
            "automation_status": self.automation_status,
            "availability_status": self.availability_status.value,
            "detected_version": self.detected_version,
            "executable_identity": self.executable_identity,
            "installation_status": self.installation_status.value,
            "live_execution_permission": self.live_execution_permission,
            "network_use": self.network_use.value,
            "notes": self.notes,
            "provider_id": self.provider_id,
            "supported_modes": sorted(self.supported_modes),
            "supported_roles": sorted(self.supported_roles),
            "supports_file_prompt": self.supports_file_prompt,
            "supports_noninteractive": self.supports_noninteractive,
            "supports_stdin_prompt": self.supports_stdin_prompt,
        }


@dataclass
class ProviderRequest:
    request_id: str
    provider_id: str
    adapter_version: str
    task_id: str
    plan_id: str
    approved_plan_fingerprint: str
    project_id: str
    session_id: str
    worktree_id: str
    starting_commit: str
    role: str
    context_or_handoff_fingerprint: str
    invocation_mode: ProviderMode
    timeout_seconds: float
    output_limit_bytes: int
    fixture_id: str | None = None
    context_artifact_path: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def binding_payload(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "approved_plan_fingerprint": self.approved_plan_fingerprint,
            "attempt_key": (self.metadata or {}).get("attempt_key"),
            "context_or_handoff_fingerprint": self.context_or_handoff_fingerprint,
            "fixture_id": self.fixture_id,
            "invocation_mode": self.invocation_mode.value,
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "provider_id": self.provider_id,
            "role": self.role,
            "session_id": self.session_id,
            "starting_commit": self.starting_commit,
            "task_id": self.task_id,
            "worktree_id": self.worktree_id,
        }

    def request_fingerprint(self) -> str:
        return fingerprint(self.binding_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "approved_plan_fingerprint": self.approved_plan_fingerprint,
            "context_artifact_path": self.context_artifact_path,
            "context_or_handoff_fingerprint": self.context_or_handoff_fingerprint,
            "created_at": self.created_at,
            "fixture_id": self.fixture_id,
            "invocation_mode": self.invocation_mode.value,
            "metadata": dict(self.metadata),
            "output_limit_bytes": self.output_limit_bytes,
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "provider_id": self.provider_id,
            "request_fingerprint": self.request_fingerprint(),
            "request_id": self.request_id,
            "role": self.role,
            "session_id": self.session_id,
            "starting_commit": self.starting_commit,
            "task_id": self.task_id,
            "timeout_seconds": self.timeout_seconds,
            "worktree_id": self.worktree_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderRequest:
        return cls(
            request_id=str(data["request_id"]),
            provider_id=str(data["provider_id"]),
            adapter_version=str(data.get("adapter_version") or PROVIDER_ADAPTER_VERSION),
            task_id=str(data["task_id"]),
            plan_id=str(data["plan_id"]),
            approved_plan_fingerprint=str(data["approved_plan_fingerprint"]),
            project_id=str(data["project_id"]),
            session_id=str(data["session_id"]),
            worktree_id=str(data["worktree_id"]),
            starting_commit=str(data["starting_commit"]),
            role=str(data["role"]),
            context_or_handoff_fingerprint=str(data["context_or_handoff_fingerprint"]),
            invocation_mode=ProviderMode(
                data.get("invocation_mode") or ProviderMode.DISABLED.value
            ),
            timeout_seconds=float(data.get("timeout_seconds") or 30.0),
            output_limit_bytes=int(data.get("output_limit_bytes") or 65536),
            fixture_id=data.get("fixture_id"),
            context_artifact_path=data.get("context_artifact_path"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ProviderResultEnvelope:
    schema_version: str
    request_id: str
    provider_id: str
    adapter_version: str
    provider_cli_version: str | None
    task_id: str
    plan_id: str
    project_id: str
    session_id: str
    worktree_id: str
    role: str
    invocation_mode: str
    automation_status: str
    executable_identity: str
    sanitized_argument_array: list[str]
    request_fingerprint: str
    context_or_handoff_fingerprint: str
    approved_plan_fingerprint: str
    starting_commit: str
    started_at: str | None
    finished_at: str | None
    duration_seconds: float | None
    exit_code: int | None
    timeout_status: bool
    cancellation_status: bool
    stdout_truncated: bool
    stderr_truncated: bool
    provider_result_status: ProviderResultStatus
    failure_class: FailureClass
    result_artifact_path: str | None
    result_fingerprint: str | None
    policy_decision: PolicyDecision
    rejection_reason: str | None
    retry_count: int
    duplicate_request_status: bool
    stdout: str = ""
    stderr: str = ""
    normalized_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "approved_plan_fingerprint": self.approved_plan_fingerprint,
            "automation_status": self.automation_status,
            "cancellation_status": self.cancellation_status,
            "context_or_handoff_fingerprint": self.context_or_handoff_fingerprint,
            "duplicate_request_status": self.duplicate_request_status,
            "duration_seconds": self.duration_seconds,
            "executable_identity": self.executable_identity,
            "exit_code": self.exit_code,
            "failure_class": self.failure_class.value,
            "finished_at": self.finished_at,
            "invocation_mode": self.invocation_mode,
            "normalized_payload": dict(self.normalized_payload),
            "plan_id": self.plan_id,
            "policy_decision": self.policy_decision.value,
            "project_id": self.project_id,
            "provider_cli_version": self.provider_cli_version,
            "provider_id": self.provider_id,
            "provider_result_status": self.provider_result_status.value,
            "rejection_reason": self.rejection_reason,
            "request_fingerprint": self.request_fingerprint,
            "request_id": self.request_id,
            "result_artifact_path": self.result_artifact_path,
            "result_fingerprint": self.result_fingerprint,
            "retry_count": self.retry_count,
            "role": self.role,
            "sanitized_argument_array": list(self.sanitized_argument_array),
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "starting_commit": self.starting_commit,
            "stderr": self.stderr,
            "stderr_truncated": self.stderr_truncated,
            "stdout": self.stdout,
            "stdout_truncated": self.stdout_truncated,
            "task_id": self.task_id,
            "timeout_status": self.timeout_status,
            "worktree_id": self.worktree_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderResultEnvelope:
        return cls(
            schema_version=str(data.get("schema_version") or PROVIDER_RESULT_SCHEMA_VERSION),
            request_id=str(data.get("request_id") or ""),
            provider_id=str(data.get("provider_id") or ""),
            adapter_version=str(data.get("adapter_version") or PROVIDER_ADAPTER_VERSION),
            provider_cli_version=data.get("provider_cli_version"),
            task_id=str(data.get("task_id") or ""),
            plan_id=str(data.get("plan_id") or ""),
            project_id=str(data.get("project_id") or ""),
            session_id=str(data.get("session_id") or ""),
            worktree_id=str(data.get("worktree_id") or ""),
            role=str(data.get("role") or ""),
            invocation_mode=str(data.get("invocation_mode") or ""),
            automation_status=str(data.get("automation_status") or AUTOMATION_DISABLED),
            executable_identity=str(data.get("executable_identity") or ""),
            sanitized_argument_array=list(data.get("sanitized_argument_array") or []),
            request_fingerprint=str(data.get("request_fingerprint") or ""),
            context_or_handoff_fingerprint=str(
                data.get("context_or_handoff_fingerprint") or ""
            ),
            approved_plan_fingerprint=str(data.get("approved_plan_fingerprint") or ""),
            starting_commit=str(data.get("starting_commit") or ""),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_seconds=data.get("duration_seconds"),
            exit_code=data.get("exit_code"),
            timeout_status=bool(data.get("timeout_status")),
            cancellation_status=bool(data.get("cancellation_status")),
            stdout_truncated=bool(data.get("stdout_truncated")),
            stderr_truncated=bool(data.get("stderr_truncated")),
            provider_result_status=ProviderResultStatus(
                data.get("provider_result_status") or ProviderResultStatus.ERROR.value
            ),
            failure_class=FailureClass(
                data.get("failure_class") or FailureClass.PROVIDER_ERROR.value
            ),
            result_artifact_path=data.get("result_artifact_path"),
            result_fingerprint=data.get("result_fingerprint"),
            policy_decision=PolicyDecision(
                data.get("policy_decision") or PolicyDecision.DENY.value
            ),
            rejection_reason=data.get("rejection_reason"),
            retry_count=int(data.get("retry_count") or 0),
            duplicate_request_status=bool(data.get("duplicate_request_status")),
            stdout=str(data.get("stdout") or ""),
            stderr=str(data.get("stderr") or ""),
            normalized_payload=dict(data.get("normalized_payload") or {}),
        )


def rejected_provider_result(
    request: ProviderRequest,
    *,
    reason: str,
    failure_class: FailureClass = FailureClass.POLICY_REJECTED,
    status: ProviderResultStatus = ProviderResultStatus.REJECTED,
    duplicate: bool = False,
    automation_status: str = AUTOMATION_DISABLED,
    executable_identity: str = "",
    argv: list[str] | None = None,
) -> ProviderResultEnvelope:
    now = utc_now_iso()
    return ProviderResultEnvelope(
        schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
        request_id=request.request_id,
        provider_id=request.provider_id,
        adapter_version=request.adapter_version,
        provider_cli_version=None,
        task_id=request.task_id,
        plan_id=request.plan_id,
        project_id=request.project_id,
        session_id=request.session_id,
        worktree_id=request.worktree_id,
        role=request.role,
        invocation_mode=request.invocation_mode.value,
        automation_status=automation_status,
        executable_identity=executable_identity,
        sanitized_argument_array=list(argv or []),
        request_fingerprint=request.request_fingerprint(),
        context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
        approved_plan_fingerprint=request.approved_plan_fingerprint,
        starting_commit=request.starting_commit,
        started_at=now,
        finished_at=now,
        duration_seconds=0.0,
        exit_code=None,
        timeout_status=False,
        cancellation_status=status is ProviderResultStatus.CANCELLED,
        stdout_truncated=False,
        stderr_truncated=False,
        provider_result_status=status,
        failure_class=failure_class,
        result_artifact_path=None,
        result_fingerprint=None,
        policy_decision=PolicyDecision.DENY,
        rejection_reason=reason,
        retry_count=0,
        duplicate_request_status=duplicate,
    )


REQUIRED_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "provider_id",
        "adapter_version",
        "task_id",
        "plan_id",
        "project_id",
        "session_id",
        "worktree_id",
        "role",
        "invocation_mode",
        "automation_status",
        "executable_identity",
        "sanitized_argument_array",
        "request_fingerprint",
        "context_or_handoff_fingerprint",
        "approved_plan_fingerprint",
        "starting_commit",
        "provider_result_status",
        "failure_class",
        "policy_decision",
        "retry_count",
        "duplicate_request_status",
        "timeout_status",
        "cancellation_status",
        "stdout_truncated",
        "stderr_truncated",
    }
)


def validate_provider_result_dict(data: dict[str, Any]) -> list[str]:
    """Return list of validation errors; empty means acceptable for intake."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["result must be a mapping"]
    for key in sorted(REQUIRED_RESULT_FIELDS):
        if key not in data:
            errors.append(f"missing required field: {key}")
    schema = data.get("schema_version")
    if schema and schema != PROVIDER_RESULT_SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version {schema!r}; expected {PROVIDER_RESULT_SCHEMA_VERSION}"
        )
    status = data.get("provider_result_status")
    if status == ProviderResultStatus.SUCCESS.value:
        if not data.get("result_artifact_path") and not data.get("normalized_payload"):
            errors.append("successful result requires artifact path or normalized_payload")
        if data.get("failure_class") not in (FailureClass.NONE.value, None):
            if data.get("failure_class") != FailureClass.NONE.value:
                errors.append("successful result must have failure_class=none")
    if data.get("policy_decision") == PolicyDecision.DENY.value and status == ProviderResultStatus.SUCCESS.value:
        errors.append("deny policy cannot be success")
    return errors


def is_provider_result_intake_ready(envelope: ProviderResultEnvelope) -> bool:
    if envelope.policy_decision is not PolicyDecision.ALLOW:
        return False
    if envelope.provider_result_status is not ProviderResultStatus.SUCCESS:
        return False
    if envelope.failure_class is not FailureClass.NONE:
        return False
    errors = validate_provider_result_dict(envelope.to_dict())
    return not errors
