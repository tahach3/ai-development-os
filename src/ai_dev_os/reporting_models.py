"""Round 4C evidence-first reporting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .fingerprints import fingerprint
from .models import utc_now_iso
from .reporting_constants import (
    EVIDENCE_SCHEMA_VERSION,
    REDACTION_POLICY_VERSION,
    RELEVANCE_POLICY_VERSION,
    RENDERER_VERSION,
    REPORT_POLICY_VERSION,
    REPORT_SCHEMA_VERSION,
)


class ReportAudience(str, Enum):
    EXECUTIVE = "executive"
    OPERATOR = "operator"
    DEVELOPER = "developer"
    INDEPENDENT_REVIEWER = "independent_reviewer"
    AUDITOR = "auditor"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    STANDARD = "standard"
    FULL = "full"
    AUDIT = "audit"


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    REPORTED = "reported"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class ReportStatus(str, Enum):
    COMPLETE = "complete"
    COMPLETE_WITH_NOTES = "complete_with_notes"
    INCOMPLETE = "incomplete"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    BLOCKED = "blocked"
    INVALID = "invalid"
    STALE = "stale"


class EvidenceType(str, Enum):
    TASK = "task"
    PLAN = "approval_plan"
    APPROVAL = "approval"
    GIT_INSPECTION = "git_inspection"
    WORKTREE_SESSION = "worktree_session"
    IMPLEMENTATION_RESULT = "implementation_result"
    COMMAND_RESULT = "command_result"
    TARGETED_TEST_RESULT = "targeted_test_result"
    FULL_TEST_RESULT = "full_test_result"
    REVIEW_VERDICT = "review_verdict"
    REVIEW_FINDING = "review_finding"
    REPAIR_ROUND = "repair_round"
    ORCHESTRATION_EVENT = "orchestration_event"
    PROVIDER_RESULT = "provider_result"
    PROVIDER_READINESS = "provider_readiness"
    CI_STAGE = "ci_stage"
    CI_RUN = "ci_run"
    PR_VALIDATION = "pr_validation"
    DEPENDENCY_CHECK = "dependency_check"
    SECRET_SCAN = "secret_scan"
    SECURITY_POLICY_DECISION = "security_policy_decision"
    HUMAN_DECISION = "human_decision"
    ROOT_CAUSE = "root_cause"
    RISK = "risk"
    USAGE = "usage"
    LEGACY_REPORT = "legacy_report"
    SYNTHETIC = "synthetic"


class AuthorityLevel(str, Enum):
    AUTHORITATIVE_PERSISTED = "authoritative_persisted"
    DETERMINISTIC_DERIVED = "deterministic_derived"
    AGENT_REPORTED = "agent_reported"
    OPERATOR_SUPPLIED = "operator_supplied"
    EXTERNAL_UNVERIFIED = "external_unverified"


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class AvailabilityState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class UsageEvidenceState(str, Enum):
    MEASURED = "measured"
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class CriterionStatus(str, Enum):
    PASSED = "passed"
    PASSED_WITH_NOTES = "passed_with_notes"
    FAILED = "failed"
    NOT_VERIFIED = "not_verified"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class SecuritySeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class RootCauseConfidence(str, Enum):
    CONFIRMED = "confirmed"
    STRONGLY_SUPPORTED = "strongly_supported"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    UNRESOLVED = "unresolved"


class RelevanceDecisionKind(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    COLLAPSED = "collapsed"


class LegacySupportMark(str, Enum):
    LEGACY_SUPPORTED = "legacy_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED_VERSION = "unsupported_version"


class PrivacyClassification(str, Enum):
    PUBLIC_SAFE = "public_safe"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    AUDIT_ONLY = "audit_only"


class RetentionClass(str, Enum):
    EPHEMERAL = "ephemeral"
    TASK_LIFETIME = "task_lifetime"
    PROJECT_HISTORY = "project_history"
    AUDIT_REQUIRED = "audit_required"


class ReportingFailureClass(str, Enum):
    NONE = "none"
    SCHEMA_INVALID = "schema_invalid"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    STALE_SOURCE = "stale_source"
    MISSING_MANDATORY_EVIDENCE = "missing_mandatory_evidence"
    DANGLING_REFERENCE = "dangling_reference"
    DUPLICATE_EVIDENCE_ID = "duplicate_evidence_id"
    UNSUPPORTED_VERSION = "unsupported_version"
    PROHIBITED_PATH = "prohibited_path"
    REDACTION_REQUIRED = "redaction_required"
    CONFLICTING_MATERIAL = "conflicting_material"
    BLOCKED_WORKFLOW = "blocked_workflow"
    INTERNAL_ERROR = "internal_error"


def normalize_claim_status(raw: str | None) -> ClaimStatus:
    if raw is None or raw == "" or raw == "unknown":
        return ClaimStatus.UNAVAILABLE
    return ClaimStatus(raw)


def new_evidence_id(prefix: str = "ev") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def new_report_id(*, source_set_fp: str, audience: str, detail: str) -> str:
    """Collision-safe deterministic report ID from semantic binding keys."""
    digest = fingerprint(
        {
            "source_set_fingerprint": source_set_fp,
            "audience": audience,
            "detail_level": detail,
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_policy_version": REPORT_POLICY_VERSION,
        }
    )
    return f"rpt_{digest[:16]}"


@dataclass
class EvidenceItem:
    evidence_id: str
    evidence_type: EvidenceType
    source_type: str
    source_record_type: str
    source_record_id: str
    structured_value: dict[str, Any] = field(default_factory=dict)
    safe_summary: str = ""
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    source_path: str | None = None
    source_commit: str | None = None
    source_fingerprint: str | None = None
    collected_at: str = field(default_factory=utc_now_iso)
    effective_at: str | None = None
    freshness_status: FreshnessStatus = FreshnessStatus.FRESH
    authority_level: AuthorityLevel = AuthorityLevel.AGENT_REPORTED
    verification_method: str | None = None
    verification_status: ClaimStatus = ClaimStatus.REPORTED
    claim_ids_supported: list[str] = field(default_factory=list)
    claim_ids_contradicted: list[str] = field(default_factory=list)
    sensitivity_classification: PrivacyClassification = PrivacyClassification.INTERNAL
    redaction_status: str = "none"
    truncation_status: str = "none"
    integrity_hash: str | None = None
    producer: str = "ai-dev-os"
    producer_version: str | None = None
    policy_version: str = REPORT_POLICY_VERSION
    availability_state: AvailabilityState = AvailabilityState.AVAILABLE
    failure_class: str | None = None
    notes: str | None = None
    legacy_support: LegacySupportMark | None = None

    def compute_integrity_hash(self) -> str:
        payload = self.to_dict()
        payload.pop("integrity_hash", None)
        payload.pop("collected_at", None)
        self.integrity_hash = fingerprint(payload)
        return self.integrity_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "schema_version": self.schema_version,
            "evidence_type": self.evidence_type.value,
            "source_type": self.source_type,
            "source_record_type": self.source_record_type,
            "source_record_id": self.source_record_id,
            "source_path": self.source_path,
            "source_commit": self.source_commit,
            "source_fingerprint": self.source_fingerprint,
            "collected_at": self.collected_at,
            "effective_at": self.effective_at,
            "freshness_status": self.freshness_status.value,
            "authority_level": self.authority_level.value,
            "verification_method": self.verification_method,
            "verification_status": self.verification_status.value,
            "claim_ids_supported": list(self.claim_ids_supported),
            "claim_ids_contradicted": list(self.claim_ids_contradicted),
            "structured_value": dict(self.structured_value),
            "safe_summary": self.safe_summary,
            "sensitivity_classification": self.sensitivity_classification.value,
            "redaction_status": self.redaction_status,
            "truncation_status": self.truncation_status,
            "integrity_hash": self.integrity_hash,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "policy_version": self.policy_version,
            "availability_state": self.availability_state.value,
            "failure_class": self.failure_class,
            "notes": self.notes,
            "legacy_support": self.legacy_support.value if self.legacy_support else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceItem:
        legacy = data.get("legacy_support")
        return cls(
            evidence_id=data["evidence_id"],
            schema_version=data.get("schema_version", EVIDENCE_SCHEMA_VERSION),
            evidence_type=EvidenceType(data["evidence_type"]),
            source_type=data.get("source_type", "unknown"),
            source_record_type=data.get("source_record_type", "unknown"),
            source_record_id=str(data.get("source_record_id", "")),
            source_path=data.get("source_path"),
            source_commit=data.get("source_commit"),
            source_fingerprint=data.get("source_fingerprint"),
            collected_at=data.get("collected_at") or utc_now_iso(),
            effective_at=data.get("effective_at"),
            freshness_status=FreshnessStatus(data.get("freshness_status", "fresh")),
            authority_level=AuthorityLevel(data.get("authority_level", "agent_reported")),
            verification_method=data.get("verification_method"),
            verification_status=normalize_claim_status(data.get("verification_status")),
            claim_ids_supported=list(data.get("claim_ids_supported") or []),
            claim_ids_contradicted=list(data.get("claim_ids_contradicted") or []),
            structured_value=dict(data.get("structured_value") or {}),
            safe_summary=data.get("safe_summary") or "",
            sensitivity_classification=PrivacyClassification(
                data.get("sensitivity_classification", "internal")
            ),
            redaction_status=data.get("redaction_status") or "none",
            truncation_status=data.get("truncation_status") or "none",
            integrity_hash=data.get("integrity_hash"),
            producer=data.get("producer") or "ai-dev-os",
            producer_version=data.get("producer_version"),
            policy_version=data.get("policy_version") or REPORT_POLICY_VERSION,
            availability_state=AvailabilityState(data.get("availability_state", "available")),
            failure_class=data.get("failure_class"),
            notes=data.get("notes"),
            legacy_support=LegacySupportMark(legacy) if legacy else None,
        )


@dataclass
class ClaimRecord:
    claim_id: str
    text: str
    status: ClaimStatus
    evidence_ids: list[str] = field(default_factory=list)
    inference_rule_id: str | None = None
    applicability_reason: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "status": self.status.value,
            "evidence_ids": list(self.evidence_ids),
            "inference_rule_id": self.inference_rule_id,
            "applicability_reason": self.applicability_reason,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClaimRecord:
        return cls(
            claim_id=data["claim_id"],
            text=data.get("text") or "",
            status=normalize_claim_status(data.get("status")),
            evidence_ids=list(data.get("evidence_ids") or []),
            inference_rule_id=data.get("inference_rule_id"),
            applicability_reason=data.get("applicability_reason"),
            notes=data.get("notes"),
        )


@dataclass
class AcceptanceCriterionRow:
    criterion_id: str
    criterion_text: str
    status: CriterionStatus
    claim_status: ClaimStatus
    evidence_ids: list[str] = field(default_factory=list)
    verification_method: str | None = None
    verifier: str | None = None
    unresolved_issue: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion_text": self.criterion_text,
            "status": self.status.value,
            "claim_status": self.claim_status.value,
            "evidence_ids": list(self.evidence_ids),
            "verification_method": self.verification_method,
            "verifier": self.verifier,
            "unresolved_issue": self.unresolved_issue,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceCriterionRow:
        return cls(
            criterion_id=data["criterion_id"],
            criterion_text=data.get("criterion_text") or "",
            status=CriterionStatus(data.get("status", "not_verified")),
            claim_status=normalize_claim_status(data.get("claim_status")),
            evidence_ids=list(data.get("evidence_ids") or []),
            verification_method=data.get("verification_method"),
            verifier=data.get("verifier"),
            unresolved_issue=data.get("unresolved_issue"),
            notes=data.get("notes"),
        )


@dataclass
class RelevanceDecision:
    section_id: str
    decision: RelevanceDecisionKind
    rule_id: str
    reason: str
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "decision": self.decision.value,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelevanceDecision:
        return cls(
            section_id=data["section_id"],
            decision=RelevanceDecisionKind(data["decision"]),
            rule_id=data.get("rule_id") or "",
            reason=data.get("reason") or "",
            priority=int(data.get("priority") or 0),
        )


@dataclass
class RiskRecord:
    risk_id: str
    category: str
    severity: SecuritySeverity
    description: str
    status: str = "open"
    likelihood: str | None = None
    impact: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    mitigation: str | None = None
    owner: str | None = None
    approval_requirement: bool = False
    blocking: bool = False
    accepted_by: str | None = None
    accepted_at: str | None = None
    review_by: str | None = None
    residual_risk: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "category": self.category,
            "severity": self.severity.value,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "status": self.status,
            "description": self.description,
            "evidence_ids": list(self.evidence_ids),
            "mitigation": self.mitigation,
            "owner": self.owner,
            "approval_requirement": self.approval_requirement,
            "blocking": self.blocking,
            "accepted_by": self.accepted_by,
            "accepted_at": self.accepted_at,
            "review_by": self.review_by,
            "residual_risk": self.residual_risk,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskRecord:
        return cls(
            risk_id=data["risk_id"],
            category=data.get("category") or "general",
            severity=SecuritySeverity(data.get("severity", "medium")),
            likelihood=data.get("likelihood"),
            impact=data.get("impact"),
            status=data.get("status") or "open",
            description=data.get("description") or "",
            evidence_ids=list(data.get("evidence_ids") or []),
            mitigation=data.get("mitigation"),
            owner=data.get("owner"),
            approval_requirement=bool(data.get("approval_requirement")),
            blocking=bool(data.get("blocking")),
            accepted_by=data.get("accepted_by"),
            accepted_at=data.get("accepted_at"),
            review_by=data.get("review_by"),
            residual_risk=data.get("residual_risk"),
        )


@dataclass
class NextAction:
    action_id: str
    text: str
    action_type: str
    required: bool = True
    order: int = 0
    related_blocker_ids: list[str] = field(default_factory=list)
    related_risk_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "text": self.text,
            "action_type": self.action_type,
            "required": self.required,
            "order": self.order,
            "related_blocker_ids": list(self.related_blocker_ids),
            "related_risk_ids": list(self.related_risk_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NextAction:
        return cls(
            action_id=data["action_id"],
            text=data.get("text") or "",
            action_type=data.get("action_type") or "operator",
            required=bool(data.get("required", True)),
            order=int(data.get("order") or 0),
            related_blocker_ids=list(data.get("related_blocker_ids") or []),
            related_risk_ids=list(data.get("related_risk_ids") or []),
        )


@dataclass
class RootCauseRecord:
    root_cause_id: str
    observed_failure: str
    failure_class: str
    confidence: RootCauseConfidence
    first_detected_at: str | None = None
    affected_stage: str | None = None
    affected_components: list[str] = field(default_factory=list)
    immediate_cause: str | None = None
    contributing_factors: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    ruled_out_causes: list[str] = field(default_factory=list)
    correction: str | None = None
    verification_performed: str | None = None
    recurrence_prevention: str | None = None
    residual_risk: str | None = None
    status: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_cause_id": self.root_cause_id,
            "observed_failure": self.observed_failure,
            "failure_class": self.failure_class,
            "first_detected_at": self.first_detected_at,
            "affected_stage": self.affected_stage,
            "affected_components": list(self.affected_components),
            "immediate_cause": self.immediate_cause,
            "contributing_factors": list(self.contributing_factors),
            "evidence_ids": list(self.evidence_ids),
            "ruled_out_causes": list(self.ruled_out_causes),
            "confidence": self.confidence.value,
            "correction": self.correction,
            "verification_performed": self.verification_performed,
            "recurrence_prevention": self.recurrence_prevention,
            "residual_risk": self.residual_risk,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RootCauseRecord:
        return cls(
            root_cause_id=data["root_cause_id"],
            observed_failure=data.get("observed_failure") or "",
            failure_class=data.get("failure_class") or "unknown",
            first_detected_at=data.get("first_detected_at"),
            affected_stage=data.get("affected_stage"),
            affected_components=list(data.get("affected_components") or []),
            immediate_cause=data.get("immediate_cause"),
            contributing_factors=list(data.get("contributing_factors") or []),
            evidence_ids=list(data.get("evidence_ids") or []),
            ruled_out_causes=list(data.get("ruled_out_causes") or []),
            confidence=RootCauseConfidence(data.get("confidence", "unresolved")),
            correction=data.get("correction"),
            verification_performed=data.get("verification_performed"),
            recurrence_prevention=data.get("recurrence_prevention"),
            residual_risk=data.get("residual_risk"),
            status=data.get("status") or "open",
        )


@dataclass
class UsageField:
    name: str
    state: UsageEvidenceState
    value: Any = None
    unit: str | None = None
    method: str | None = None
    assumptions: str | None = None
    currency: str | None = None
    pricing_source: str | None = None
    pricing_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "value": self.value,
            "unit": self.unit,
            "method": self.method,
            "assumptions": self.assumptions,
            "currency": self.currency,
            "pricing_source": self.pricing_source,
            "pricing_version": self.pricing_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageField:
        state = UsageEvidenceState(data.get("state", "unavailable"))
        value = data.get("value")
        if state in (UsageEvidenceState.UNAVAILABLE, UsageEvidenceState.NOT_APPLICABLE):
            value = None
        return cls(
            name=data.get("name") or "unknown",
            state=state,
            value=value,
            unit=data.get("unit"),
            method=data.get("method"),
            assumptions=data.get("assumptions"),
            currency=data.get("currency"),
            pricing_source=data.get("pricing_source"),
            pricing_version=data.get("pricing_version"),
        )


@dataclass
class SecurityFinding:
    finding_id: str
    severity: SecuritySeverity
    status: str
    title: str
    description: str
    affected_scope: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    remediation: str | None = None
    owner: str | None = None
    blocking: bool = False
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity.value,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "affected_scope": self.affected_scope,
            "evidence_ids": list(self.evidence_ids),
            "remediation": self.remediation,
            "owner": self.owner,
            "blocking": self.blocking,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityFinding:
        return cls(
            finding_id=data["finding_id"],
            severity=SecuritySeverity(data.get("severity", "informational")),
            status=data.get("status") or "open",
            title=data.get("title") or "",
            description=data.get("description") or "",
            affected_scope=data.get("affected_scope"),
            evidence_ids=list(data.get("evidence_ids") or []),
            remediation=data.get("remediation"),
            owner=data.get("owner"),
            blocking=bool(data.get("blocking")),
            resolution=data.get("resolution"),
        )


@dataclass
class RedactionEvent:
    event_id: str
    category: str
    field_path: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "category": self.category,
            "field_path": self.field_path,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RedactionEvent:
        return cls(
            event_id=data["event_id"],
            category=data.get("category") or "secret",
            field_path=data.get("field_path") or "",
            reason=data.get("reason") or "",
        )


@dataclass
class SectionRecord:
    section_id: str
    title: str
    content: dict[str, Any] = field(default_factory=dict)
    included: bool = True
    collapsed: bool = False
    omission_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": dict(self.content),
            "included": self.included,
            "collapsed": self.collapsed,
            "omission_reason": self.omission_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectionRecord:
        return cls(
            section_id=data["section_id"],
            title=data.get("title") or data["section_id"],
            content=dict(data.get("content") or {}),
            included=bool(data.get("included", True)),
            collapsed=bool(data.get("collapsed", False)),
            omission_reason=data.get("omission_reason"),
        )


@dataclass
class CanonicalReportSnapshot:
    report_id: str
    audience: ReportAudience
    detail_level: DetailLevel
    report_status: ReportStatus
    project_id: str
    task_id: str
    task_objective: str
    outcome: str
    final_verdict: str
    schema_version: str = REPORT_SCHEMA_VERSION
    report_policy_version: str = REPORT_POLICY_VERSION
    relevance_policy_version: str = RELEVANCE_POLICY_VERSION
    redaction_policy_version: str = REDACTION_POLICY_VERSION
    renderer_version: str = RENDERER_VERSION
    generated_at: str = field(default_factory=utc_now_iso)
    plan_id: str | None = None
    orchestration_id: str | None = None
    ci_run_ids: list[str] = field(default_factory=list)
    starting_commit: str | None = None
    final_commit: str | None = None
    repository_identity: str | None = None
    acceptance_criteria: list[AcceptanceCriterionRow] = field(default_factory=list)
    section_records: list[SectionRecord] = field(default_factory=list)
    claim_records: list[ClaimRecord] = field(default_factory=list)
    evidence_manifest: list[EvidenceItem] = field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any]] = field(default_factory=list)
    unavailable_mandatory: list[str] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    risks: list[RiskRecord] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[NextAction] = field(default_factory=list)
    root_causes: list[RootCauseRecord] = field(default_factory=list)
    security_findings: list[SecurityFinding] = field(default_factory=list)
    usage_fields: list[UsageField] = field(default_factory=list)
    relevance_decisions: list[RelevanceDecision] = field(default_factory=list)
    redaction_events: list[RedactionEvent] = field(default_factory=list)
    privacy_classification: PrivacyClassification = PrivacyClassification.INTERNAL
    retention_classification: RetentionClass = RetentionClass.TASK_LIFETIME
    report_fingerprint: str | None = None
    source_set_fingerprint: str | None = None
    source_bindings: dict[str, Any] = field(default_factory=dict)
    ordering_metadata: dict[str, Any] = field(default_factory=dict)
    failure_class: ReportingFailureClass = ReportingFailureClass.NONE
    executive_summary: dict[str, Any] = field(default_factory=dict)
    git_intelligence: dict[str, Any] = field(default_factory=dict)
    test_intelligence: dict[str, Any] = field(default_factory=dict)
    ci_intelligence: dict[str, Any] = field(default_factory=dict)
    dependency_intelligence: dict[str, Any] = field(default_factory=dict)
    provider_orchestration: dict[str, Any] = field(default_factory=dict)
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    documentation_only: bool = False
    legacy_marks: list[str] = field(default_factory=list)
    rendered_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "schema_version": self.schema_version,
            "report_policy_version": self.report_policy_version,
            "relevance_policy_version": self.relevance_policy_version,
            "redaction_policy_version": self.redaction_policy_version,
            "renderer_version": self.renderer_version,
            "generated_at": self.generated_at,
            "report_status": self.report_status.value,
            "audience": self.audience.value,
            "detail_level": self.detail_level.value,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "orchestration_id": self.orchestration_id,
            "ci_run_ids": list(self.ci_run_ids),
            "starting_commit": self.starting_commit,
            "final_commit": self.final_commit,
            "repository_identity": self.repository_identity,
            "task_objective": self.task_objective,
            "acceptance_criteria": [r.to_dict() for r in self.acceptance_criteria],
            "outcome": self.outcome,
            "final_verdict": self.final_verdict,
            "section_records": [s.to_dict() for s in self.section_records],
            "claim_records": [c.to_dict() for c in self.claim_records],
            "evidence_manifest": [e.to_dict() for e in self.evidence_manifest],
            "unresolved_conflicts": list(self.unresolved_conflicts),
            "unavailable_mandatory": list(self.unavailable_mandatory),
            "approvals": list(self.approvals),
            "risks": [r.to_dict() for r in self.risks],
            "blockers": list(self.blockers),
            "next_actions": [n.to_dict() for n in self.next_actions],
            "root_causes": [r.to_dict() for r in self.root_causes],
            "security_findings": [s.to_dict() for s in self.security_findings],
            "usage_fields": [u.to_dict() for u in self.usage_fields],
            "relevance_decisions": [d.to_dict() for d in self.relevance_decisions],
            "redaction_events": [e.to_dict() for e in self.redaction_events],
            "privacy_classification": self.privacy_classification.value,
            "retention_classification": self.retention_classification.value,
            "report_fingerprint": self.report_fingerprint,
            "source_set_fingerprint": self.source_set_fingerprint,
            "source_bindings": dict(self.source_bindings),
            "ordering_metadata": dict(self.ordering_metadata),
            "failure_class": self.failure_class.value,
            "executive_summary": dict(self.executive_summary),
            "git_intelligence": dict(self.git_intelligence),
            "test_intelligence": dict(self.test_intelligence),
            "ci_intelligence": dict(self.ci_intelligence),
            "dependency_intelligence": dict(self.dependency_intelligence),
            "provider_orchestration": dict(self.provider_orchestration),
            "repair_history": list(self.repair_history),
            "documentation_only": self.documentation_only,
            "legacy_marks": list(self.legacy_marks),
            "rendered_paths": dict(self.rendered_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalReportSnapshot:
        return cls(
            report_id=data["report_id"],
            schema_version=data.get("schema_version", REPORT_SCHEMA_VERSION),
            report_policy_version=data.get("report_policy_version", REPORT_POLICY_VERSION),
            relevance_policy_version=data.get(
                "relevance_policy_version", RELEVANCE_POLICY_VERSION
            ),
            redaction_policy_version=data.get(
                "redaction_policy_version", REDACTION_POLICY_VERSION
            ),
            renderer_version=data.get("renderer_version", RENDERER_VERSION),
            generated_at=data.get("generated_at") or utc_now_iso(),
            report_status=ReportStatus(data.get("report_status", "incomplete")),
            audience=ReportAudience(data["audience"]),
            detail_level=DetailLevel(data["detail_level"]),
            project_id=data.get("project_id") or "",
            task_id=data.get("task_id") or "",
            plan_id=data.get("plan_id"),
            orchestration_id=data.get("orchestration_id"),
            ci_run_ids=list(data.get("ci_run_ids") or []),
            starting_commit=data.get("starting_commit"),
            final_commit=data.get("final_commit"),
            repository_identity=data.get("repository_identity"),
            task_objective=data.get("task_objective") or "",
            acceptance_criteria=[
                AcceptanceCriterionRow.from_dict(r)
                for r in (data.get("acceptance_criteria") or [])
            ],
            outcome=data.get("outcome") or "",
            final_verdict=data.get("final_verdict") or "",
            section_records=[
                SectionRecord.from_dict(s) for s in (data.get("section_records") or [])
            ],
            claim_records=[ClaimRecord.from_dict(c) for c in (data.get("claim_records") or [])],
            evidence_manifest=[
                EvidenceItem.from_dict(e) for e in (data.get("evidence_manifest") or [])
            ],
            unresolved_conflicts=list(data.get("unresolved_conflicts") or []),
            unavailable_mandatory=list(data.get("unavailable_mandatory") or []),
            approvals=list(data.get("approvals") or []),
            risks=[RiskRecord.from_dict(r) for r in (data.get("risks") or [])],
            blockers=list(data.get("blockers") or []),
            next_actions=[NextAction.from_dict(n) for n in (data.get("next_actions") or [])],
            root_causes=[RootCauseRecord.from_dict(r) for r in (data.get("root_causes") or [])],
            security_findings=[
                SecurityFinding.from_dict(s) for s in (data.get("security_findings") or [])
            ],
            usage_fields=[UsageField.from_dict(u) for u in (data.get("usage_fields") or [])],
            relevance_decisions=[
                RelevanceDecision.from_dict(d) for d in (data.get("relevance_decisions") or [])
            ],
            redaction_events=[
                RedactionEvent.from_dict(e) for e in (data.get("redaction_events") or [])
            ],
            privacy_classification=PrivacyClassification(
                data.get("privacy_classification", "internal")
            ),
            retention_classification=RetentionClass(
                data.get("retention_classification", "task_lifetime")
            ),
            report_fingerprint=data.get("report_fingerprint"),
            source_set_fingerprint=data.get("source_set_fingerprint"),
            source_bindings=dict(data.get("source_bindings") or {}),
            ordering_metadata=dict(data.get("ordering_metadata") or {}),
            failure_class=ReportingFailureClass(data.get("failure_class", "none")),
            executive_summary=dict(data.get("executive_summary") or {}),
            git_intelligence=dict(data.get("git_intelligence") or {}),
            test_intelligence=dict(data.get("test_intelligence") or {}),
            ci_intelligence=dict(data.get("ci_intelligence") or {}),
            dependency_intelligence=dict(data.get("dependency_intelligence") or {}),
            provider_orchestration=dict(data.get("provider_orchestration") or {}),
            repair_history=list(data.get("repair_history") or []),
            documentation_only=bool(data.get("documentation_only")),
            legacy_marks=list(data.get("legacy_marks") or []),
            rendered_paths=dict(data.get("rendered_paths") or {}),
        )
