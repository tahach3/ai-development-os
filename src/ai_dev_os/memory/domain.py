"""Shared-memory domain enums and immutable models (Phase B3.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from ai_dev_os.models import utc_now_iso

from .versions import MEMORY_SCHEMA_VERSION

# ID prefixes locked in Phase B2 §3 / §6.
MEMORY_ID_RE = re.compile(r"^mem-[0-9a-f]{12}$")
MEMORY_EVENT_ID_RE = re.compile(r"^mev-[0-9a-f]{12}$")
MEMORY_LINK_ID_RE = re.compile(r"^mlk-[0-9a-f]{12}$")
MEMORY_EVIDENCE_ID_RE = re.compile(r"^evid-[0-9a-f]{12}$")


class MemoryClass(str, Enum):
    """Durable memory classes. ephemeral_context is never persisted."""

    CANDIDATE = "candidate_memory"
    APPROVED = "approved_memory"
    REJECTED = "rejected_memory"
    SUPERSEDED = "superseded_memory"
    ARCHIVED = "archived_memory"


class LifecycleStatus(str, Enum):
    """Lifecycle status — distinct from MemoryClass."""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    SECRET_PROHIBITED = "secret_prohibited"


class EvidenceStrength(str, Enum):
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class MemoryCategory(str, Enum):
    PROJECT_FACT = "project_fact"
    ARCHITECTURE_DECISION = "architecture_decision"
    USER_PREFERENCE = "user_preference"
    ACCEPTED_PLAN_REF = "accepted_plan_ref"
    INCIDENT_CONSTRAINT = "incident_constraint"
    PROVIDER_BEHAVIOR = "provider_behavior"
    LESSON = "lesson"
    OPERATIONAL_OBSERVATION = "operational_observation"
    OTHER = "other"


class MemorySourceType(str, Enum):
    OPERATOR = "operator"
    CLAUDE = "claude"
    CURSOR = "cursor"
    CODEX = "codex"
    SYSTEM = "system"
    ORCHESTRATION = "orchestration"


class MemoryActorRole(str, Enum):
    """Actors for pure authorization checks. Models cannot approve."""

    OS_CONTROL_PLANE = "os_control_plane"
    HUMAN_OPERATOR = "human_operator"
    CLAUDE = "claude"
    CURSOR = "cursor"
    CODEX = "codex"
    PROVIDER = "provider"
    ORCHESTRATION = "orchestration"


class ApprovalMethod(str, Enum):
    HUMAN = "human"
    # Reserved for a future policy path — not authorized in the prototype.
    POLICY = "policy"


class LinkType(str, Enum):
    SUPERSEDES = "supersedes"
    SUPERSEDED_BY = "superseded_by"
    DUPLICATE_OF = "duplicate_of"
    CHALLENGES = "challenges"
    RELATED = "related"


class MemoryEvidenceType(str, Enum):
    PLAN_FINGERPRINT = "plan_fingerprint"
    TEST_RUN = "test_run"
    CI_RUN = "ci_run"
    REVIEW_VERDICT = "review_verdict"
    COMMIT_SHA = "commit_sha"
    HANDOFF_FINGERPRINT = "handoff_fingerprint"
    OPERATOR_NOTE = "operator_note"
    OTHER = "other"


class MemoryAction(str, Enum):
    PROPOSE = "propose"
    VALIDATE = "validate"
    APPROVE = "approve"
    REJECT = "reject"
    SUPERSEDE = "supersede"
    ARCHIVE = "archive"
    FORGET = "forget"
    HARD_DELETE = "hard_delete"


# Typical class ↔ status pairings (B2 §6.8). Forgotten may apply after any prior class.
CLASS_STATUS_PAIRINGS: dict[MemoryClass, frozenset[LifecycleStatus]] = {
    MemoryClass.CANDIDATE: frozenset(
        {LifecycleStatus.PROPOSED, LifecycleStatus.VALIDATED, LifecycleStatus.FORGOTTEN}
    ),
    MemoryClass.APPROVED: frozenset(
        {LifecycleStatus.APPROVED, LifecycleStatus.FORGOTTEN}
    ),
    MemoryClass.REJECTED: frozenset(
        {LifecycleStatus.REJECTED, LifecycleStatus.FORGOTTEN}
    ),
    MemoryClass.SUPERSEDED: frozenset(
        {LifecycleStatus.SUPERSEDED, LifecycleStatus.FORGOTTEN}
    ),
    MemoryClass.ARCHIVED: frozenset(
        {LifecycleStatus.ARCHIVED, LifecycleStatus.FORGOTTEN}
    ),
}


def new_memory_id() -> str:
    return f"mem-{uuid4().hex[:12]}"


def new_memory_event_id() -> str:
    return f"mev-{uuid4().hex[:12]}"


def new_memory_link_id() -> str:
    return f"mlk-{uuid4().hex[:12]}"


def new_memory_evidence_id() -> str:
    return f"evid-{uuid4().hex[:12]}"


def is_valid_memory_id(value: str) -> bool:
    return bool(MEMORY_ID_RE.fullmatch(value))


def is_valid_memory_event_id(value: str) -> bool:
    return bool(MEMORY_EVENT_ID_RE.fullmatch(value))


def is_valid_memory_link_id(value: str) -> bool:
    return bool(MEMORY_LINK_ID_RE.fullmatch(value))


def is_valid_memory_evidence_id(value: str) -> bool:
    return bool(MEMORY_EVIDENCE_ID_RE.fullmatch(value))


@dataclass(frozen=True)
class MemoryEvidenceRef:
    evidence_id: str
    evidence_type: MemoryEvidenceType
    evidence_ref: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "evidence_ref": self.evidence_ref,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEvidenceRef:
        return cls(
            evidence_id=str(data["evidence_id"]),
            evidence_type=MemoryEvidenceType(data["evidence_type"]),
            evidence_ref=str(data["evidence_ref"]),
            note=data.get("note"),
        )


@dataclass(frozen=True)
class MemoryLink:
    link_id: str
    project_id: str
    from_memory_id: str
    to_memory_id: str
    link_type: LinkType
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "project_id": self.project_id,
            "from_memory_id": self.from_memory_id,
            "to_memory_id": self.to_memory_id,
            "link_type": self.link_type.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryLink:
        return cls(
            link_id=str(data["link_id"]),
            project_id=str(data["project_id"]),
            from_memory_id=str(data["from_memory_id"]),
            to_memory_id=str(data["to_memory_id"]),
            link_type=LinkType(data["link_type"]),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass(frozen=True)
class MemoryRecord:
    """Immutable in-memory domain record (not persisted in B3.1)."""

    memory_id: str
    project_id: str
    category: MemoryCategory
    content: str
    proposed_by: str
    source_type: MemorySourceType
    memory_class: MemoryClass = MemoryClass.CANDIDATE
    lifecycle_status: LifecycleStatus = LifecycleStatus.PROPOSED
    title: str | None = None
    content_normalized: str | None = None
    content_hash: str | None = None
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    confidence: float | None = None
    provider_id: str | None = None
    task_id: str | None = None
    plan_fingerprint: str | None = None
    session_id: str | None = None
    orchestration_id: str | None = None
    approved_by: str | None = None
    approval_method: ApprovalMethod | None = None
    rejection_reason: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes_memory_id: str | None = None
    superseded_by_memory_id: str | None = None
    forgotten_at: str | None = None
    content_erased_at: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    validated_at: str | None = None
    approved_at: str | None = None
    schema_version: str = MEMORY_SCHEMA_VERSION
    evidence: tuple[MemoryEvidenceRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "memory_class": self.memory_class.value,
            "lifecycle_status": self.lifecycle_status.value,
            "category": self.category.value,
            "title": self.title,
            "content": self.content,
            "content_normalized": self.content_normalized,
            "content_hash": self.content_hash,
            "sensitivity": self.sensitivity.value,
            "evidence_strength": self.evidence_strength.value,
            "confidence": self.confidence,
            "source_type": self.source_type.value,
            "proposed_by": self.proposed_by,
            "provider_id": self.provider_id,
            "task_id": self.task_id,
            "plan_fingerprint": self.plan_fingerprint,
            "session_id": self.session_id,
            "orchestration_id": self.orchestration_id,
            "approved_by": self.approved_by,
            "approval_method": (
                self.approval_method.value if self.approval_method else None
            ),
            "rejection_reason": self.rejection_reason,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "supersedes_memory_id": self.supersedes_memory_id,
            "superseded_by_memory_id": self.superseded_by_memory_id,
            "forgotten_at": self.forgotten_at,
            "content_erased_at": self.content_erased_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "validated_at": self.validated_at,
            "approved_at": self.approved_at,
            "schema_version": self.schema_version,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        evidence_raw = data.get("evidence") or []
        approval_method = data.get("approval_method")
        return cls(
            memory_id=str(data["memory_id"]),
            project_id=str(data["project_id"]),
            memory_class=MemoryClass(data.get("memory_class", MemoryClass.CANDIDATE.value)),
            lifecycle_status=LifecycleStatus(
                data.get("lifecycle_status", LifecycleStatus.PROPOSED.value)
            ),
            category=MemoryCategory(data["category"]),
            title=data.get("title"),
            content=str(data["content"]),
            content_normalized=data.get("content_normalized"),
            content_hash=data.get("content_hash"),
            sensitivity=Sensitivity(data.get("sensitivity", Sensitivity.INTERNAL.value)),
            evidence_strength=EvidenceStrength(
                data.get("evidence_strength", EvidenceStrength.NONE.value)
            ),
            confidence=data.get("confidence"),
            source_type=MemorySourceType(data["source_type"]),
            proposed_by=str(data["proposed_by"]),
            provider_id=data.get("provider_id"),
            task_id=data.get("task_id"),
            plan_fingerprint=data.get("plan_fingerprint"),
            session_id=data.get("session_id"),
            orchestration_id=data.get("orchestration_id"),
            approved_by=data.get("approved_by"),
            approval_method=(
                ApprovalMethod(approval_method) if approval_method else None
            ),
            rejection_reason=data.get("rejection_reason"),
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
            supersedes_memory_id=data.get("supersedes_memory_id"),
            superseded_by_memory_id=data.get("superseded_by_memory_id"),
            forgotten_at=data.get("forgotten_at"),
            content_erased_at=data.get("content_erased_at"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            validated_at=data.get("validated_at"),
            approved_at=data.get("approved_at"),
            schema_version=str(data.get("schema_version") or MEMORY_SCHEMA_VERSION),
            evidence=tuple(MemoryEvidenceRef.from_dict(e) for e in evidence_raw),
        )
