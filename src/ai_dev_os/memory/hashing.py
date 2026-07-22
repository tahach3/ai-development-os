"""Memory content hashing via existing canonical JSON + SHA-256 helpers.

Memory fingerprints deliberately wrap ``ai_dev_os.fingerprints.canonical_json``
and ``sha256_hex`` so Round 4C/4D1 hashing contracts stay untouched. The wrapper
adds memory-specific payload shaping and ``MEMORY_FINGERPRINT_VERSION`` only.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ai_dev_os.fingerprints import canonical_json, sha256_hex

from .domain import MemoryEvidenceRef, MemoryRecord
from .versions import (
    MEMORY_FINGERPRINT_VERSION,
    MEMORY_NORMALIZATION_VERSION,
    MEMORY_SCHEMA_VERSION,
)


def memory_canonical_json(payload: Any) -> str:
    """Stable JSON serialization — delegates to shared ``canonical_json``."""
    return canonical_json(payload)


def memory_sha256_hex(payload: Any) -> str:
    """SHA-256 of canonical JSON — delegates to shared ``sha256_hex``."""
    return sha256_hex(payload)


def _sorted_evidence_refs(
    evidence: Sequence[MemoryEvidenceRef] | Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in evidence:
        if isinstance(item, MemoryEvidenceRef):
            items.append(
                {
                    "evidence_id": item.evidence_id,
                    "evidence_type": item.evidence_type.value,
                    "evidence_ref": item.evidence_ref,
                }
            )
        else:
            items.append(
                {
                    "evidence_id": str(item["evidence_id"]),
                    "evidence_type": str(item["evidence_type"]),
                    "evidence_ref": str(item["evidence_ref"]),
                }
            )
    return sorted(
        items,
        key=lambda e: (e["evidence_type"], e["evidence_ref"], e["evidence_id"]),
    )


def build_memory_fingerprint_payload(
    *,
    project_id: str,
    category: str,
    content_normalized: str,
    sensitivity: str,
    memory_class: str,
    lifecycle_status: str,
    evidence_strength: str,
    source_type: str,
    proposed_by: str,
    title: str | None = None,
    evidence: Sequence[MemoryEvidenceRef] | Iterable[Mapping[str, Any]] = (),
    provider_id: str | None = None,
    task_id: str | None = None,
    plan_fingerprint: str | None = None,
    session_id: str | None = None,
    orchestration_id: str | None = None,
) -> dict[str, Any]:
    """Fingerprint payload per B2 §8.5 (excludes volatile timestamps / approval meta)."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "category": category,
        "title": title,
        "content_normalized": content_normalized,
        "sensitivity": sensitivity,
        "memory_class": memory_class,
        "lifecycle_status": lifecycle_status,
        "evidence_strength": evidence_strength,
        "evidence_refs": _sorted_evidence_refs(evidence),
        "source_type": source_type,
        "proposed_by": proposed_by,
        "provider_id": provider_id,
        "task_id": task_id,
        "plan_fingerprint": plan_fingerprint,
        "session_id": session_id,
        "orchestration_id": orchestration_id,
        "memory_fingerprint_version": MEMORY_FINGERPRINT_VERSION,
        "memory_normalization_version": MEMORY_NORMALIZATION_VERSION,
        "memory_schema_version": MEMORY_SCHEMA_VERSION,
    }
    return payload


def fingerprint_payload_from_record(record: MemoryRecord) -> dict[str, Any]:
    if not record.content_normalized:
        raise ValueError("content_normalized is required before fingerprinting")
    return build_memory_fingerprint_payload(
        project_id=record.project_id,
        category=record.category.value,
        content_normalized=record.content_normalized,
        sensitivity=record.sensitivity.value,
        memory_class=record.memory_class.value,
        lifecycle_status=record.lifecycle_status.value,
        evidence_strength=record.evidence_strength.value,
        source_type=record.source_type.value,
        proposed_by=record.proposed_by,
        title=record.title,
        evidence=record.evidence,
        provider_id=record.provider_id,
        task_id=record.task_id,
        plan_fingerprint=record.plan_fingerprint,
        session_id=record.session_id,
        orchestration_id=record.orchestration_id,
    )


def compute_content_hash(payload: Mapping[str, Any] | MemoryRecord) -> str:
    if isinstance(payload, MemoryRecord):
        data = fingerprint_payload_from_record(payload)
    else:
        data = dict(payload)
    return memory_sha256_hex(data)
