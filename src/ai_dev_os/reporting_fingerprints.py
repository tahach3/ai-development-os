"""Report integrity fingerprints for Round 4C."""

from __future__ import annotations

from typing import Any

from .fingerprints import fingerprint
from .reporting_constants import (
    REDACTION_POLICY_VERSION,
    RELEVANCE_POLICY_VERSION,
    REPORT_FP_EXCLUDE,
    REPORT_POLICY_VERSION,
    REPORT_SCHEMA_VERSION,
)
from .reporting_models import CanonicalReportSnapshot, EvidenceItem


def source_set_fingerprint(
    *,
    evidence: list[EvidenceItem],
    bindings: dict[str, Any],
) -> str:
    evidence_hashes = sorted(
        e.integrity_hash or e.compute_integrity_hash() for e in evidence
    )
    payload = {
        "bindings": {k: bindings[k] for k in sorted(bindings)},
        "evidence_hashes": evidence_hashes,
        "report_policy_version": REPORT_POLICY_VERSION,
        "relevance_policy_version": RELEVANCE_POLICY_VERSION,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "schema_version": REPORT_SCHEMA_VERSION,
    }
    return fingerprint(payload)


def report_fingerprint_payload(snapshot: CanonicalReportSnapshot) -> dict[str, Any]:
    data = snapshot.to_dict()
    for key in REPORT_FP_EXCLUDE:
        data.pop(key, None)
    # Drop volatile nested generated markers if any
    data.pop("rendered_paths", None)
    return data


def compute_report_fingerprint(snapshot: CanonicalReportSnapshot) -> str:
    return fingerprint(report_fingerprint_payload(snapshot))
