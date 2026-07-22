"""Validate canonical reports: schema, fingerprints, freshness, references."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .reporting_constants import (
    EVIDENCE_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
)
from .reporting_fingerprints import compute_report_fingerprint, source_set_fingerprint
from .reporting_models import (
    CanonicalReportSnapshot,
    ClaimStatus,
    ReportStatus,
    ReportingFailureClass,
)


@dataclass
class ValidationResult:
    ok: bool
    report_status: ReportStatus | None = None
    failure_class: ReportingFailureClass = ReportingFailureClass.NONE
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "report_status": self.report_status.value if self.report_status else None,
            "failure_class": self.failure_class.value,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def validate_snapshot(
    snapshot: CanonicalReportSnapshot,
    *,
    current_bindings: dict[str, Any] | None = None,
    allow_incomplete_diagnostic: bool = False,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if snapshot.schema_version != REPORT_SCHEMA_VERSION:
        errors.append(f"unsupported_report_schema:{snapshot.schema_version}")

    ev_ids = [e.evidence_id for e in snapshot.evidence_manifest]
    if len(ev_ids) != len(set(ev_ids)):
        errors.append("duplicate_evidence_id")

    known = set(ev_ids)
    for claim in snapshot.claim_records:
        if not claim.status:
            errors.append(f"missing_claim_status:{claim.claim_id}")
        if claim.status is ClaimStatus.VERIFIED and not claim.evidence_ids:
            errors.append(f"verified_without_evidence:{claim.claim_id}")
        if claim.status is ClaimStatus.INFERRED and not claim.inference_rule_id:
            errors.append(f"inferred_without_rule:{claim.claim_id}")
        for eid in claim.evidence_ids:
            if eid not in known:
                errors.append(f"dangling_reference:{eid}")

    for ev in snapshot.evidence_manifest:
        if ev.schema_version not in (EVIDENCE_SCHEMA_VERSION, REPORT_SCHEMA_VERSION) and not str(
            ev.schema_version
        ).startswith("4c."):
            if not ev.legacy_support:
                errors.append(f"unsupported_evidence_schema:{ev.evidence_id}")

    expected_sfp = source_set_fingerprint(
        evidence=list(snapshot.evidence_manifest),
        bindings=dict(snapshot.source_bindings),
    )
    if snapshot.source_set_fingerprint and snapshot.source_set_fingerprint != expected_sfp:
        errors.append("source_set_fingerprint_mismatch")

    # Recompute report fingerprint with same exclusion rules
    tmp = CanonicalReportSnapshot.from_dict(snapshot.to_dict())
    tmp.report_fingerprint = None
    expected_rfp = compute_report_fingerprint(tmp)
    if snapshot.report_fingerprint and snapshot.report_fingerprint != expected_rfp:
        errors.append("report_fingerprint_mismatch")

    stale = False
    if current_bindings:
        for key in (
            "task_fingerprint",
            "plan_fingerprint",
            "approval_fingerprint",
            "starting_commit",
            "final_commit",
            "report_policy_version",
            "relevance_policy_version",
            "redaction_policy_version",
        ):
            if key in current_bindings and key in snapshot.source_bindings:
                if current_bindings[key] != snapshot.source_bindings[key]:
                    stale = True
                    errors.append(f"stale_source:{key}")

    status = snapshot.report_status
    failure = ReportingFailureClass.NONE
    if any(e.startswith("unsupported_") for e in errors):
        status = ReportStatus.INVALID
        failure = ReportingFailureClass.UNSUPPORTED_VERSION
    elif any("fingerprint_mismatch" in e for e in errors):
        status = ReportStatus.INVALID
        failure = ReportingFailureClass.INTEGRITY_MISMATCH
    elif stale or any(e.startswith("stale_source:") for e in errors):
        status = ReportStatus.STALE
        failure = ReportingFailureClass.STALE_SOURCE
    elif any(e.startswith("dangling_") or e.startswith("duplicate_") for e in errors):
        status = ReportStatus.INVALID
        failure = ReportingFailureClass.DANGLING_REFERENCE
    elif snapshot.unavailable_mandatory and status not in (
        ReportStatus.INCOMPLETE,
        ReportStatus.BLOCKED,
        ReportStatus.CONFLICTING_EVIDENCE,
    ):
        warnings.append("unavailable_mandatory_present")

    ok = not errors
    if allow_incomplete_diagnostic and status in (
        ReportStatus.INCOMPLETE,
        ReportStatus.STALE,
        ReportStatus.BLOCKED,
    ):
        # Diagnostic path: structural integrity may still fail
        ok = not any(
            x in failure.value
            for x in ("integrity", "dangling", "duplicate", "unsupported", "schema")
        ) and not any(
            e.startswith("duplicate_")
            or e.startswith("dangling_")
            or e.startswith("unsupported_")
            or "fingerprint_mismatch" in e
            for e in errors
        )
        # For stale diagnostic, fingerprint/schema ok but stale keys are expected
        if status is ReportStatus.STALE:
            ok = not any("fingerprint_mismatch" in e or e.startswith("duplicate_") for e in errors)

    return ValidationResult(
        ok=ok,
        report_status=status,
        failure_class=failure if errors else snapshot.failure_class,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
    )


def is_stale_against(
    snapshot: CanonicalReportSnapshot,
    current_bindings: dict[str, Any],
) -> bool:
    result = validate_snapshot(snapshot, current_bindings=current_bindings)
    return result.report_status is ReportStatus.STALE or any(
        e.startswith("stale_source:") for e in result.errors
    )
