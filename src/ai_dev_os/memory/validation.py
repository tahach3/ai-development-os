"""Pure validation, lifecycle transitions, and authorization for memory."""

from __future__ import annotations

from typing import Any

from .domain import (
    CLASS_STATUS_PAIRINGS,
    ApprovalMethod,
    EvidenceStrength,
    LifecycleStatus,
    MemoryAction,
    MemoryActorRole,
    MemoryCategory,
    MemoryClass,
    MemoryEvidenceRef,
    MemoryRecord,
    MemorySourceType,
    Sensitivity,
    is_valid_memory_evidence_id,
    is_valid_memory_event_id,
    is_valid_memory_id,
    is_valid_memory_link_id,
)
from .errors import (
    MemoryAuthorizationError,
    MemoryConflictError,
    MemorySecurityError,
    MemoryValidationError,
)
from .hashing import compute_content_hash, fingerprint_payload_from_record
from .normalization import normalize_memory_content, refuse_secrets_in_text

# Pure lifecycle graph (status only). Class updates are paired separately.
LIFECYCLE_TRANSITIONS: dict[LifecycleStatus, frozenset[LifecycleStatus]] = {
    LifecycleStatus.PROPOSED: frozenset(
        {
            LifecycleStatus.VALIDATED,
            LifecycleStatus.REJECTED,
            LifecycleStatus.FORGOTTEN,
        }
    ),
    LifecycleStatus.VALIDATED: frozenset(
        {
            LifecycleStatus.APPROVED,
            LifecycleStatus.REJECTED,
            LifecycleStatus.FORGOTTEN,
        }
    ),
    LifecycleStatus.APPROVED: frozenset(
        {
            LifecycleStatus.SUPERSEDED,
            LifecycleStatus.ARCHIVED,
            LifecycleStatus.FORGOTTEN,
        }
    ),
    LifecycleStatus.REJECTED: frozenset({LifecycleStatus.FORGOTTEN}),
    LifecycleStatus.SUPERSEDED: frozenset(
        {LifecycleStatus.ARCHIVED, LifecycleStatus.FORGOTTEN}
    ),
    LifecycleStatus.ARCHIVED: frozenset({LifecycleStatus.FORGOTTEN}),
    LifecycleStatus.FORGOTTEN: frozenset(),
}

STATUS_TO_CLASS: dict[LifecycleStatus, MemoryClass] = {
    LifecycleStatus.PROPOSED: MemoryClass.CANDIDATE,
    LifecycleStatus.VALIDATED: MemoryClass.CANDIDATE,
    LifecycleStatus.APPROVED: MemoryClass.APPROVED,
    LifecycleStatus.REJECTED: MemoryClass.REJECTED,
    LifecycleStatus.SUPERSEDED: MemoryClass.SUPERSEDED,
    LifecycleStatus.ARCHIVED: MemoryClass.ARCHIVED,
}

# Models / providers may propose only. Humans + OS gate mutations.
_MODEL_LIKE = frozenset(
    {
        MemoryActorRole.CLAUDE,
        MemoryActorRole.CURSOR,
        MemoryActorRole.CODEX,
        MemoryActorRole.PROVIDER,
        MemoryActorRole.ORCHESTRATION,
    }
)

ACTION_ALLOWED_ROLES: dict[MemoryAction, frozenset[MemoryActorRole]] = {
    MemoryAction.PROPOSE: frozenset(MemoryActorRole),
    MemoryAction.VALIDATE: frozenset({MemoryActorRole.OS_CONTROL_PLANE}),
    MemoryAction.APPROVE: frozenset(
        {MemoryActorRole.HUMAN_OPERATOR, MemoryActorRole.OS_CONTROL_PLANE}
    ),
    MemoryAction.REJECT: frozenset(
        {MemoryActorRole.HUMAN_OPERATOR, MemoryActorRole.OS_CONTROL_PLANE}
    ),
    MemoryAction.SUPERSEDE: frozenset(
        {MemoryActorRole.HUMAN_OPERATOR, MemoryActorRole.OS_CONTROL_PLANE}
    ),
    MemoryAction.ARCHIVE: frozenset(
        {MemoryActorRole.HUMAN_OPERATOR, MemoryActorRole.OS_CONTROL_PLANE}
    ),
    MemoryAction.FORGET: frozenset(
        {MemoryActorRole.HUMAN_OPERATOR, MemoryActorRole.OS_CONTROL_PLANE}
    ),
    MemoryAction.HARD_DELETE: frozenset({MemoryActorRole.HUMAN_OPERATOR}),
}


def validate_memory_id(value: str, *, kind: str = "memory_id") -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryValidationError(f"{kind} must be a non-empty string")
    checkers = {
        "memory_id": is_valid_memory_id,
        "event_id": is_valid_memory_event_id,
        "link_id": is_valid_memory_link_id,
        "evidence_id": is_valid_memory_evidence_id,
    }
    check = checkers.get(kind, is_valid_memory_id)
    if not check(value):
        raise MemoryValidationError(f"Invalid {kind} format: {value!r}")
    return value


def validate_class_status_pairing(
    memory_class: MemoryClass, lifecycle_status: LifecycleStatus
) -> None:
    allowed = CLASS_STATUS_PAIRINGS.get(memory_class, frozenset())
    if lifecycle_status not in allowed:
        raise MemoryValidationError(
            f"Invalid class/status pairing: {memory_class.value} / "
            f"{lifecycle_status.value}"
        )


def validate_lifecycle_transition(
    current: LifecycleStatus, new: LifecycleStatus
) -> None:
    if current == new:
        return
    allowed = LIFECYCLE_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise MemoryConflictError(
            f"Invalid memory lifecycle transition: {current.value} → {new.value}. "
            f"Allowed: {sorted(s.value for s in allowed) or 'none'}"
        )


def expected_class_for_status(status: LifecycleStatus) -> MemoryClass | None:
    """Return the class for a non-forgotten status; forgotten keeps prior class."""
    return STATUS_TO_CLASS.get(status)


def authorize_memory_action(actor: MemoryActorRole, action: MemoryAction) -> None:
    """Fail closed if the actor may not perform ``action``. Models cannot approve."""
    if actor in _MODEL_LIKE and action is not MemoryAction.PROPOSE:
        raise MemoryAuthorizationError(
            f"Actor role {actor.value} may propose only; refused action={action.value}"
        )
    allowed = ACTION_ALLOWED_ROLES.get(action, frozenset())
    if actor not in allowed:
        raise MemoryAuthorizationError(
            f"Actor role {actor.value} is not authorized for action={action.value}"
        )


def validate_sensitivity_for_persist(sensitivity: Sensitivity) -> None:
    if sensitivity is Sensitivity.SECRET_PROHIBITED:
        raise MemorySecurityError(
            "sensitivity=secret_prohibited is refused before persist"
        )


def validate_evidence_ref(ref: MemoryEvidenceRef) -> None:
    validate_memory_id(ref.evidence_id, kind="evidence_id")
    if not ref.evidence_ref or not str(ref.evidence_ref).strip():
        raise MemoryValidationError("evidence_ref must be non-empty")
    if ref.note is not None:
        refuse_secrets_in_text(ref.note, path="memory:evidence_note")


def validate_memory_record_fields(record: MemoryRecord) -> None:
    validate_memory_id(record.memory_id, kind="memory_id")
    if not record.project_id or not str(record.project_id).strip():
        raise MemoryValidationError("project_id must be non-empty")
    if not record.proposed_by or not str(record.proposed_by).strip():
        raise MemoryValidationError("proposed_by must be non-empty")
    if not isinstance(record.category, MemoryCategory):
        raise MemoryValidationError("category must be a MemoryCategory")
    if not isinstance(record.source_type, MemorySourceType):
        raise MemoryValidationError("source_type must be a MemorySourceType")
    if not isinstance(record.evidence_strength, EvidenceStrength):
        raise MemoryValidationError("evidence_strength must be EvidenceStrength")
    validate_class_status_pairing(record.memory_class, record.lifecycle_status)
    validate_sensitivity_for_persist(record.sensitivity)
    if record.confidence is not None:
        if not isinstance(record.confidence, (int, float)):
            raise MemoryValidationError("confidence must be a number")
        if record.confidence < 0.0 or record.confidence > 1.0:
            raise MemoryValidationError("confidence must be between 0.0 and 1.0")
    if record.lifecycle_status is LifecycleStatus.REJECTED and not (
        record.rejection_reason and str(record.rejection_reason).strip()
    ):
        raise MemoryValidationError("rejection_reason is required when rejected")
    if record.lifecycle_status is LifecycleStatus.APPROVED:
        if not (record.approved_by and str(record.approved_by).strip()):
            raise MemoryValidationError("approved_by is required when approved")
        if record.approval_method is not ApprovalMethod.HUMAN:
            raise MemoryValidationError(
                "approval_method must be human in the prototype"
            )
    for ev in record.evidence:
        validate_evidence_ref(ev)
    refuse_secrets_in_text(record.content, path="memory:content")
    if record.title:
        refuse_secrets_in_text(record.title, path="memory:title")


def prepare_candidate_record(record: MemoryRecord) -> MemoryRecord:
    """Validate + normalize + hash a propose-time candidate (pure; no I/O)."""
    if record.memory_class is not MemoryClass.CANDIDATE:
        raise MemoryValidationError("propose path requires memory_class=candidate_memory")
    if record.lifecycle_status is not LifecycleStatus.PROPOSED:
        raise MemoryValidationError("propose path requires lifecycle_status=proposed")
    validate_memory_record_fields(record)
    normalized = normalize_memory_content(record.content)
    # Rebuild with derived fields via replace pattern (frozen).
    data = record.to_dict()
    data["content_normalized"] = normalized
    interim = MemoryRecord.from_dict(data)
    payload = fingerprint_payload_from_record(interim)
    data["content_hash"] = compute_content_hash(payload)
    prepared = MemoryRecord.from_dict(data)
    validate_memory_record_fields(prepared)
    return prepared


def validate_content_hash(record: MemoryRecord, *, expected: str | None = None) -> str:
    """Recompute content hash; mismatch fails closed (stale candidate)."""
    if not record.content_normalized:
        raise MemoryValidationError("content_normalized required for hash check")
    actual = compute_content_hash(record)
    target = expected if expected is not None else record.content_hash
    if not target:
        raise MemoryValidationError("content_hash is missing")
    if actual != target:
        raise MemoryConflictError("content_hash mismatch (stale or tampered candidate)")
    return actual


def validate_propose_dict(data: dict[str, Any]) -> MemoryRecord:
    """Build and prepare a candidate from a mapping (fail closed)."""
    if not isinstance(data, dict):
        raise MemoryValidationError("Memory payload must be a mapping")
    required = ("project_id", "category", "content", "proposed_by", "source_type")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise MemoryValidationError(
            f"Missing required memory fields: {', '.join(missing)}"
        )
    payload = dict(data)
    payload.setdefault("memory_class", MemoryClass.CANDIDATE.value)
    payload.setdefault("lifecycle_status", LifecycleStatus.PROPOSED.value)
    payload.setdefault("sensitivity", Sensitivity.INTERNAL.value)
    payload.setdefault("evidence_strength", EvidenceStrength.NONE.value)
    if "memory_id" not in payload or not payload["memory_id"]:
        from .domain import new_memory_id

        payload["memory_id"] = new_memory_id()
    try:
        record = MemoryRecord.from_dict(payload)
    except (KeyError, ValueError, TypeError) as exc:
        raise MemoryValidationError(f"Invalid memory payload: {exc}") from exc
    return prepare_candidate_record(record)
