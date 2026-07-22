"""Adapters from legacy Round 1–4B records into Round 4C evidence (read-only)."""

from __future__ import annotations

from typing import Any

from .fingerprints import fingerprint_implementation_report, fingerprint_review_report
from .models import ImplementationReport, ReviewReport, TokenUsageMode
from .reporting_models import (
    AuthorityLevel,
    AvailabilityState,
    ClaimStatus,
    EvidenceItem,
    EvidenceType,
    LegacySupportMark,
    UsageEvidenceState,
    UsageField,
    new_evidence_id,
)


def adapt_implementation_report(report: ImplementationReport) -> EvidenceItem:
    data = report.to_dict()
    fp = report.content_fingerprint or fingerprint_implementation_report(data)
    return EvidenceItem(
        evidence_id=new_evidence_id("leg_impl"),
        evidence_type=EvidenceType.LEGACY_REPORT,
        source_type="workspace_report",
        source_record_type="implementation_report",
        source_record_id=report.task_id,
        source_fingerprint=fp,
        authority_level=AuthorityLevel.AGENT_REPORTED,
        verification_status=ClaimStatus.REPORTED,
        structured_value={
            "outcome": report.outcome.value,
            "summary": report.summary,
            "files_changed": list(report.files_changed),
            "tests_run": list(report.tests_run),
        },
        safe_summary=f"Legacy implementation report for {report.task_id}: {report.outcome.value}",
        legacy_support=LegacySupportMark.LEGACY_SUPPORTED,
        notes="Historical implementation report; claims are reported unless independently verified",
    )


def adapt_review_report(report: ReviewReport) -> EvidenceItem:
    data = report.to_dict()
    fp = report.content_fingerprint or fingerprint_review_report(data)
    return EvidenceItem(
        evidence_id=new_evidence_id("leg_rev"),
        evidence_type=EvidenceType.REVIEW_VERDICT,
        source_type="workspace_report",
        source_record_type="review_report",
        source_record_id=report.task_id,
        source_fingerprint=fp,
        authority_level=AuthorityLevel.AGENT_REPORTED,
        verification_status=ClaimStatus.REPORTED,
        structured_value={
            "verdict": report.verdict.value,
            "reviewer_role": report.reviewer_role.value,
            "findings_count": len(report.findings),
        },
        safe_summary=f"Legacy review for {report.task_id}: {report.verdict.value}",
        legacy_support=LegacySupportMark.LEGACY_SUPPORTED,
    )


def adapt_token_usage(token: dict[str, Any] | None) -> UsageField:
    if not token:
        return UsageField(name="token_usage", state=UsageEvidenceState.UNAVAILABLE, value=None)
    mode = token.get("mode", TokenUsageMode.UNAVAILABLE.value)
    if mode == TokenUsageMode.UNAVAILABLE.value or mode == "unknown":
        return UsageField(name="token_usage", state=UsageEvidenceState.UNAVAILABLE, value=None)
    if mode == TokenUsageMode.ESTIMATED.value:
        return UsageField(
            name="total_tokens",
            state=UsageEvidenceState.ESTIMATED,
            value=(token.get("input_tokens") or 0) + (token.get("output_tokens") or 0)
            if token.get("input_tokens") is not None or token.get("output_tokens") is not None
            else None,
            method=token.get("notes") or "legacy_estimated",
        )
    if mode == "provider_reported":
        return UsageField(
            name="total_tokens",
            state=UsageEvidenceState.PROVIDER_REPORTED,
            value=None
            if token.get("input_tokens") is None and token.get("output_tokens") is None
            else (token.get("input_tokens") or 0) + (token.get("output_tokens") or 0),
        )
    if mode == TokenUsageMode.MEASURED.value:
        return UsageField(
            name="total_tokens",
            state=UsageEvidenceState.MEASURED,
            value=(token.get("input_tokens") or 0) + (token.get("output_tokens") or 0)
            if token.get("input_tokens") is not None or token.get("output_tokens") is not None
            else None,
        )
    return UsageField(name="token_usage", state=UsageEvidenceState.UNAVAILABLE, value=None)


def adapt_partial_legacy(data: dict[str, Any]) -> EvidenceItem:
    """Mark incomplete legacy payloads without promoting missing fields to verified."""
    return EvidenceItem(
        evidence_id=new_evidence_id("leg_partial"),
        evidence_type=EvidenceType.LEGACY_REPORT,
        source_type="workspace_report",
        source_record_type=str(data.get("record_type") or "unknown_legacy"),
        source_record_id=str(data.get("id") or "unknown"),
        authority_level=AuthorityLevel.EXTERNAL_UNVERIFIED,
        verification_status=ClaimStatus.UNAVAILABLE,
        availability_state=AvailabilityState.PARTIAL,
        structured_value={"keys_present": sorted(data.keys())},
        safe_summary="Partial legacy evidence; insufficient for verification",
        legacy_support=LegacySupportMark.INSUFFICIENT_EVIDENCE,
    )
