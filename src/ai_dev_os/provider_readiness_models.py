"""Round 4D1 provider-readiness controlled vocabularies and records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .fingerprints import fingerprint
from .models import utc_now_iso
from .provider_readiness_constants import (
    AUTHENTICATION_PROBE_POLICY_VERSION,
    EXECUTABLE_TRUST_POLICY_VERSION,
    HOST_SYSTEM_VERDICT_SCHEMA_VERSION,
    NONINTERACTIVE_CONTRACT_POLICY_VERSION,
    READINESS_POLICY_VERSION,
    READINESS_SCHEMA_VERSION,
    ROLE_ELIGIBILITY_POLICY_VERSION,
    SAFE_RUNNER_POLICY_VERSION,
    VERSION_COMPATIBILITY_POLICY_VERSION,
)


class DiscoveryStatus(str, Enum):
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    AMBIGUOUS_INSTALLATION = "ambiguous_installation"
    EXECUTABLE_UNTRUSTED = "executable_untrusted"
    PROBE_FAILED = "probe_failed"


class CompatibilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIED = "unverified"
    MALFORMED = "malformed"
    UNAVAILABLE = "unavailable"


class AuthenticationStatus(str, Enum):
    AUTHENTICATED_VERIFIED = "authenticated_verified"
    UNAUTHENTICATED_VERIFIED = "unauthenticated_verified"
    REPORTED_AUTHENTICATED = "reported_authenticated"
    UNKNOWN = "unknown"
    VERIFICATION_UNSUPPORTED = "verification_unsupported"
    VERIFICATION_FAILED = "verification_failed"


class NoninteractiveStatus(str, Enum):
    SUPPORTED_VERIFIED = "supported_verified"
    SUPPORTED_DOCUMENTED = "supported_documented"
    UNSUPPORTED_VERIFIED = "unsupported_verified"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class CapabilityStatus(str, Enum):
    SUPPORTED_VERIFIED = "supported_verified"
    SUPPORTED_DOCUMENTED = "supported_documented"
    UNSUPPORTED_VERIFIED = "unsupported_verified"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class RoleEligibility(str, Enum):
    ELIGIBLE = "eligible"
    CONDITIONALLY_ELIGIBLE = "conditionally_eligible"
    INELIGIBLE = "ineligible"
    UNVERIFIED = "unverified"
    POLICY_BLOCKED = "policy_blocked"


class ReviewerIndependence(str, Enum):
    SEPARATE_PROVIDER_AVAILABLE = "separate_provider_available"
    SEPARATE_MODEL_AVAILABLE = "separate_model_available"
    FRESH_CONTEXT_SAME_PROVIDER_ONLY = "fresh_context_same_provider_only"
    INDEPENDENCE_UNVERIFIED = "independence_unverified"
    UNAVAILABLE = "unavailable"


class ReadinessVerdict(str, Enum):
    ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE = "eligible_for_bounded_live_smoke"
    CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE = (
        "conditionally_eligible_for_bounded_live_smoke"
    )
    INSTALLED_BUT_AUTHENTICATION_UNVERIFIED = "installed_but_authentication_unverified"
    INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED = "installed_but_noninteractive_unverified"
    INSTALLED_BUT_VERSION_UNSUPPORTED = "installed_but_version_unsupported"
    AMBIGUOUS_PROVIDER_INSTALLATION = "ambiguous_provider_installation"
    NO_ELIGIBLE_PROVIDER = "no_eligible_provider"
    POLICY_BLOCKED = "policy_blocked"
    PROBE_FAILED = "probe_failed"
    INVALID_RECORD = "invalid_record"


class ProbeKind(str, Enum):
    VERSION = "version"
    HELP = "help"
    AUTH_STATUS = "auth_status"


class ReadinessFailureClass(str, Enum):
    NONE = "none"
    POLICY_REJECTED = "policy_rejected"
    NOT_INSTALLED = "not_installed"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    MALFORMED_OUTPUT = "malformed_output"
    PROBE_FAILED = "probe_failed"
    AMBIGUOUS_INSTALLATION = "ambiguous_installation"
    UNTRUSTED_EXECUTABLE = "untrusted_executable"
    AUTH_UNVERIFIED = "auth_unverified"
    STALE_RECORD = "stale_record"
    EQUITIFY_REJECTED = "equitify_rejected"
    AMBIGUITY_UNRESOLVED = "ambiguity_unresolved"
    OPERATOR_SELECTION_REQUIRED = "operator_selection_required"
    EXECUTABLE_PIN_INVALID = "executable_pin_invalid"
    EXECUTABLE_PIN_STALE = "executable_pin_stale"
    WRAPPER_UNSUPPORTED = "wrapper_unsupported"
    LOGICAL_INSTALLATION_INVALID = "logical_installation_invalid"


class AuditEventType(str, Enum):
    EXECUTABLE_DISCOVERED = "executable_discovered"
    DUPLICATE_EXECUTABLE_DETECTED = "duplicate_executable_detected"
    VERSION_PROBE_ATTEMPTED = "version_probe_attempted"
    HELP_PROBE_ATTEMPTED = "help_probe_attempted"
    AUTHENTICATION_PROBE_ATTEMPTED = "authentication_probe_attempted"
    PROBE_SKIPPED_BY_SAFETY_POLICY = "probe_skipped_by_safety_policy"
    READINESS_DECISION_PRODUCED = "readiness_decision_produced"
    LIVE_INVOCATION_BLOCKED = "live_invocation_blocked"
    CANDIDATE_DISCOVERED = "candidate_discovered"
    WRAPPER_INSPECTED = "wrapper_inspected"
    TARGET_RESOLVED = "target_resolved"
    CANDIDATE_FINGERPRINTED = "candidate_fingerprinted"
    CANDIDATE_CLASSIFIED = "candidate_classified"
    LOGICAL_INSTALLATION_CREATED = "logical_installation_created"
    CANDIDATES_COLLAPSED = "candidates_collapsed"
    AMBIGUITY_RETAINED = "ambiguity_retained"
    RECOMMENDATION_PRODUCED = "recommendation_produced"
    SELECTION_REQUIRED = "selection_required"
    PIN_VALIDATED = "pin_validated"
    PIN_REJECTED = "pin_rejected"
    READINESS_RERUN = "readiness_rerun"
    AUTH_STATUS_ADVERTISED = "auth_status_advertised"
    AUTH_STATUS_NOT_ADVERTISED = "auth_status_not_advertised"
    NONINTERACTIVE_CONTRACT_ASSESSED = "noninteractive_contract_assessed"
    HOST_SYSTEM_VERDICT_PRODUCED = "host_system_verdict_produced"


READINESS_ROLES = (
    "planner",
    "implementer",
    "reviewer",
    "repair_implementer",
    "final_verifier",
)


@dataclass
class ProbeRecord:
    kind: str
    command_identity: str
    adapter_version: str
    executable_fingerprint: str | None
    timeout_seconds: float
    output_limit_bytes: int
    exit_code: int | None
    sanitized_output_summary: str
    parsed_cli_version: str | None
    parse_status: str
    failure_class: str
    skipped: bool = False
    skip_reason: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoleMatrixEntry:
    role: str
    technically_supported: bool
    adapter_supported: bool
    policy_allowed: bool
    authentication_ready: bool
    noninteractive_ready: bool
    eligibility: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderCombination:
    category: str
    implementer_provider_id: str | None
    reviewer_provider_id: str | None
    independence_status: str
    notes: str
    recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEvent:
    event_type: str
    message: str
    provider_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "details": dict(self.details),
            "event_type": self.event_type,
            "message": self.message,
            "provider_id": self.provider_id,
        }


@dataclass
class ProviderReadinessRecord:
    readiness_id: str
    schema_version: str
    readiness_policy_version: str
    generated_at: str
    project_id: str
    repository_identity: str
    repository_commit: str
    host_platform: str
    provider_id: str
    adapter_id: str
    adapter_version: str
    discovery_status: str
    executable_name: str | None
    sanitized_executable_location: str | None
    executable_fingerprint: str | None
    executable_provenance: str | None
    duplicate_executable_count: int
    selected_executable_rule: str
    cli_version: str | None
    version_verification_status: str
    compatibility_status: str
    help_probe_status: str
    authentication_status: str
    authentication_verification_method: str
    noninteractive_status: str
    noninteractive_evidence: str
    supported_roles: list[str]
    implementer_eligibility: str
    reviewer_eligibility: str
    reviewer_independence_status: str
    working_directory_binding_status: str
    isolated_worktree_compatibility: str
    structured_output_status: str
    timeout_support: str
    cancellation_support: str
    output_bounding_support: str
    environment_sanitization_support: str
    network_behavior_classification: str
    live_policy_status: str
    provider_mode_configuration: str
    blockers: list[str]
    warnings: list[str]
    evidence_references: list[str]
    source_fingerprints: dict[str, str]
    final_readiness_verdict: str
    recommended_round_4d2_role: str | None
    recommended_smoke_test_restrictions: list[str]
    record_fingerprint: str
    live_provider_invocations: int = 0
    probes: list[dict[str, Any]] = field(default_factory=list)
    role_matrix: list[dict[str, Any]] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    candidate_executables: list[dict[str, Any]] = field(default_factory=list)
    freshness_age_seconds: float | None = None
    executable_trust_policy_version: str = EXECUTABLE_TRUST_POLICY_VERSION
    version_compatibility_policy_version: str = VERSION_COMPATIBILITY_POLICY_VERSION
    authentication_probe_policy_version: str = AUTHENTICATION_PROBE_POLICY_VERSION
    noninteractive_contract_policy_version: str = NONINTERACTIVE_CONTRACT_POLICY_VERSION
    role_eligibility_policy_version: str = ROLE_ELIGIBILITY_POLICY_VERSION
    safe_runner_policy_version: str = SAFE_RUNNER_POLICY_VERSION
    host_system_verdict_schema_version: str = HOST_SYSTEM_VERDICT_SCHEMA_VERSION
    auth_status_command_advertised: bool = False
    auth_status_command_runnable: bool = False
    noninteractive_contract: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("record_fingerprint", None)
        payload.pop("generated_at", None)
        payload.pop("freshness_age_seconds", None)
        return payload

    def compute_fingerprint(self) -> str:
        return fingerprint(self.fingerprint_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "audit_events": list(self.audit_events),
            "authentication_probe_policy_version": self.authentication_probe_policy_version,
            "authentication_status": self.authentication_status,
            "authentication_verification_method": self.authentication_verification_method,
            "auth_status_command_advertised": bool(self.auth_status_command_advertised),
            "auth_status_command_runnable": bool(self.auth_status_command_runnable),
            "blockers": list(self.blockers),
            "cancellation_support": self.cancellation_support,
            "candidate_executables": list(self.candidate_executables),
            "cli_version": self.cli_version,
            "compatibility_status": self.compatibility_status,
            "discovery_status": self.discovery_status,
            "duplicate_executable_count": self.duplicate_executable_count,
            "environment_sanitization_support": self.environment_sanitization_support,
            "evidence_references": list(self.evidence_references),
            "executable_fingerprint": self.executable_fingerprint,
            "executable_name": self.executable_name,
            "executable_provenance": self.executable_provenance,
            "executable_trust_policy_version": self.executable_trust_policy_version,
            "final_readiness_verdict": self.final_readiness_verdict,
            "freshness_age_seconds": self.freshness_age_seconds,
            "generated_at": self.generated_at,
            "help_probe_status": self.help_probe_status,
            "host_platform": self.host_platform,
            "host_system_verdict_schema_version": self.host_system_verdict_schema_version,
            "implementer_eligibility": self.implementer_eligibility,
            "isolated_worktree_compatibility": self.isolated_worktree_compatibility,
            "live_policy_status": self.live_policy_status,
            "live_provider_invocations": int(self.live_provider_invocations),
            "metadata": dict(self.metadata),
            "network_behavior_classification": self.network_behavior_classification,
            "noninteractive_contract": dict(self.noninteractive_contract),
            "noninteractive_contract_policy_version": self.noninteractive_contract_policy_version,
            "noninteractive_evidence": self.noninteractive_evidence,
            "noninteractive_status": self.noninteractive_status,
            "output_bounding_support": self.output_bounding_support,
            "probes": list(self.probes),
            "project_id": self.project_id,
            "provider_id": self.provider_id,
            "provider_mode_configuration": self.provider_mode_configuration,
            "readiness_id": self.readiness_id,
            "readiness_policy_version": self.readiness_policy_version,
            "recommended_round_4d2_role": self.recommended_round_4d2_role,
            "recommended_smoke_test_restrictions": list(
                self.recommended_smoke_test_restrictions
            ),
            "record_fingerprint": self.record_fingerprint,
            "repository_commit": self.repository_commit,
            "repository_identity": self.repository_identity,
            "reviewer_eligibility": self.reviewer_eligibility,
            "reviewer_independence_status": self.reviewer_independence_status,
            "role_eligibility_policy_version": self.role_eligibility_policy_version,
            "role_matrix": list(self.role_matrix),
            "safe_runner_policy_version": self.safe_runner_policy_version,
            "sanitized_executable_location": self.sanitized_executable_location,
            "schema_version": self.schema_version,
            "selected_executable_rule": self.selected_executable_rule,
            "source_fingerprints": dict(self.source_fingerprints),
            "structured_output_status": self.structured_output_status,
            "supported_roles": list(self.supported_roles),
            "timeout_support": self.timeout_support,
            "version_compatibility_policy_version": self.version_compatibility_policy_version,
            "version_verification_status": self.version_verification_status,
            "warnings": list(self.warnings),
            "working_directory_binding_status": self.working_directory_binding_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderReadinessRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)


@dataclass
class ReadinessAuditBundle:
    """Multi-provider readiness audit result."""

    audit_id: str
    schema_version: str
    readiness_policy_version: str
    generated_at: str
    project_id: str
    repository_identity: str
    repository_commit: str
    host_platform: str
    provider_records: list[ProviderReadinessRecord]
    combinations: list[ProviderCombination]
    aggregate_verdict: str
    recommended_combination: ProviderCombination | None
    blockers: list[str]
    warnings: list[str]
    live_provider_invocations: int = 0
    host_system_verdict: str = "provider_not_eligible"
    host_system_verdict_schema_version: str = HOST_SYSTEM_VERDICT_SCHEMA_VERSION
    audit_events: list[AuditEvent] = field(default_factory=list)
    source_fingerprints: dict[str, str] = field(default_factory=dict)
    record_fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("record_fingerprint", None)
        payload.pop("generated_at", None)
        return payload

    def compute_fingerprint(self) -> str:
        return fingerprint(self.fingerprint_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregate_verdict": self.aggregate_verdict,
            "audit_events": [e.to_dict() for e in self.audit_events],
            "audit_id": self.audit_id,
            "blockers": list(self.blockers),
            "combinations": [c.to_dict() for c in self.combinations],
            "generated_at": self.generated_at,
            "host_platform": self.host_platform,
            "host_system_verdict": self.host_system_verdict,
            "host_system_verdict_schema_version": self.host_system_verdict_schema_version,
            "live_provider_invocations": int(self.live_provider_invocations),
            "metadata": dict(self.metadata),
            "project_id": self.project_id,
            "provider_records": [r.to_dict() for r in self.provider_records],
            "readiness_policy_version": self.readiness_policy_version,
            "recommended_combination": (
                self.recommended_combination.to_dict()
                if self.recommended_combination
                else None
            ),
            "record_fingerprint": self.record_fingerprint,
            "repository_commit": self.repository_commit,
            "repository_identity": self.repository_identity,
            "schema_version": self.schema_version,
            "source_fingerprints": dict(self.source_fingerprints),
            "warnings": list(self.warnings),
        }


def new_readiness_id() -> str:
    return f"prdy_{uuid4().hex[:16]}"


def new_audit_id() -> str:
    return f"raud_{uuid4().hex[:16]}"


def empty_record(
    *,
    provider_id: str,
    project_id: str,
    repository_identity: str,
    repository_commit: str,
    host_platform: str,
    adapter_version: str,
) -> ProviderReadinessRecord:
    return ProviderReadinessRecord(
        readiness_id=new_readiness_id(),
        schema_version=READINESS_SCHEMA_VERSION,
        readiness_policy_version=READINESS_POLICY_VERSION,
        generated_at=utc_now_iso(),
        project_id=project_id,
        repository_identity=repository_identity,
        repository_commit=repository_commit,
        host_platform=host_platform,
        provider_id=provider_id,
        adapter_id=provider_id,
        adapter_version=adapter_version,
        discovery_status=DiscoveryStatus.NOT_INSTALLED.value,
        executable_name=None,
        sanitized_executable_location=None,
        executable_fingerprint=None,
        executable_provenance=None,
        duplicate_executable_count=0,
        selected_executable_rule="none",
        cli_version=None,
        version_verification_status=CompatibilityStatus.UNAVAILABLE.value,
        compatibility_status=CompatibilityStatus.UNAVAILABLE.value,
        help_probe_status=CompatibilityStatus.UNAVAILABLE.value,
        authentication_status=AuthenticationStatus.VERIFICATION_UNSUPPORTED.value,
        authentication_verification_method="none",
        noninteractive_status=NoninteractiveStatus.UNAVAILABLE.value,
        noninteractive_evidence="not_assessed",
        supported_roles=[],
        implementer_eligibility=RoleEligibility.INELIGIBLE.value,
        reviewer_eligibility=RoleEligibility.INELIGIBLE.value,
        reviewer_independence_status=ReviewerIndependence.UNAVAILABLE.value,
        working_directory_binding_status=CapabilityStatus.UNAVAILABLE.value,
        isolated_worktree_compatibility=CapabilityStatus.UNAVAILABLE.value,
        structured_output_status=CapabilityStatus.UNAVAILABLE.value,
        timeout_support=CapabilityStatus.UNAVAILABLE.value,
        cancellation_support=CapabilityStatus.UNAVAILABLE.value,
        output_bounding_support=CapabilityStatus.UNAVAILABLE.value,
        environment_sanitization_support=CapabilityStatus.SUPPORTED_VERIFIED.value,
        network_behavior_classification="unknown",
        live_policy_status="disabled_for_round_4d1",
        provider_mode_configuration="unknown",
        blockers=[],
        warnings=[],
        evidence_references=[],
        source_fingerprints={},
        final_readiness_verdict=ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value,
        recommended_round_4d2_role=None,
        recommended_smoke_test_restrictions=[
            "no_live_invocation_until_separate_4d2_authorization"
        ],
        record_fingerprint="",
        live_provider_invocations=0,
    )
