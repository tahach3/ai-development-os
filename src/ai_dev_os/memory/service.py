"""Memory service layer — lifecycle orchestration over SqliteMemoryRepository.

Phase B3.3: per-project opt-in, audited transitions, no live-model wiring.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_dev_os.models import utc_now_iso
from ai_dev_os.project_registry import ProjectRegistry, ProjectRegistryError

from .config import DEFAULT_MEMORY_CONFIG, MemoryConfig
from .domain import (
    ApprovalMethod,
    EvidenceStrength,
    LifecycleStatus,
    LinkType,
    MemoryAction,
    MemoryActorRole,
    MemoryCategory,
    MemoryClass,
    MemoryLink,
    MemoryRecord,
    MemorySourceType,
    new_memory_id,
    new_memory_link_id,
)
from .errors import MemoryDisabledError, MemoryValidationError
from .sqlite_connection import initialize_memory_database
from .sqlite_repository import SqliteMemoryRepository
from .validation import (
    authorize_memory_action,
    prepare_candidate_record,
    validate_lifecycle_transition,
    validate_propose_dict,
)

_EVIDENCE_STRENGTH_RANK: dict[EvidenceStrength, int] = {
    EvidenceStrength.STRONG: 3,
    EvidenceStrength.MODERATE: 2,
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.NONE: 0,
}


def _actor_kind(role: MemoryActorRole) -> str:
    if role is MemoryActorRole.HUMAN_OPERATOR:
        return "human"
    if role is MemoryActorRole.OS_CONTROL_PLANE:
        return "system"
    return "service"


class MemoryService:
    """Project-scoped memory lifecycle over B3.2 SQLite persistence.

    Construction does not open a DB. Every operation requires the registered
    project to have ``memory_enabled=True``; otherwise ``MemoryDisabledError``.
    """

    def __init__(
        self,
        *,
        registry: ProjectRegistry,
        db_path: str | Path | None = None,
        root: str | Path | None = None,
        config: MemoryConfig | None = None,
    ) -> None:
        self._registry = registry
        base = config if config is not None else DEFAULT_MEMORY_CONFIG
        # Session config may enable SQLite only after per-project opt-in.
        self._db_path = str(db_path) if db_path is not None else base.db_path
        self._root = str(root) if root is not None else None
        self._base_config = base
        self._repo: SqliteMemoryRepository | None = None

    def _require_opt_in(self, project_id: str) -> None:
        if not project_id or not str(project_id).strip():
            raise MemoryValidationError("project_id must be non-empty")
        try:
            record = self._registry.require(project_id)
        except ProjectRegistryError as exc:
            raise MemoryDisabledError(
                f"Shared memory refused for unregistered project '{project_id}'"
            ) from exc
        if not record.memory_enabled:
            raise MemoryDisabledError(
                f"Shared memory is disabled for project '{project_id}' "
                "(memory_enabled=false). Explicit per-project opt-in required."
            )

    def _session_config(self) -> MemoryConfig:
        return MemoryConfig(
            enabled=True,
            backend=self._base_config.backend,
            db_path=self._db_path,
            default_retrieve_limit=self._base_config.default_retrieve_limit,
            max_retrieve_limit=self._base_config.max_retrieve_limit,
            busy_timeout_ms=self._base_config.busy_timeout_ms,
            audit_retrievals=self._base_config.audit_retrievals,
        )

    def _ensure_repo(self, project_id: str) -> SqliteMemoryRepository:
        self._require_opt_in(project_id)
        if self._repo is None:
            cfg = self._session_config()
            path = Path(self._db_path)
            if self._root is not None:
                root_path = Path(self._root)
            else:
                root_path = path.parent if path.is_absolute() else Path.cwd()
            if not path.is_absolute():
                path = root_path / path
            if not path.exists():
                initialize_memory_database(path, config=cfg, root=root_path)
            self._repo = SqliteMemoryRepository(
                str(path),
                config=cfg,
                root=str(root_path),
            )
        else:
            # Re-check opt-in even when repo already open.
            self._require_opt_in(project_id)
        return self._repo

    def _audit(
        self,
        repo: SqliteMemoryRepository,
        *,
        project_id: str,
        action: MemoryAction | str,
        actor: str,
        actor_role: MemoryActorRole,
        memory_id: str | None,
        before: MemoryRecord | None,
        after: MemoryRecord | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        action_value = action.value if isinstance(action, MemoryAction) else str(action)
        repo.append_event(
            project_id=project_id,
            memory_id=memory_id,
            action=action_value,
            actor=actor,
            actor_kind=_actor_kind(actor_role),
            from_class=before.memory_class.value if before else None,
            to_class=after.memory_class.value if after else None,
            from_status=before.lifecycle_status.value if before else None,
            to_status=after.lifecycle_status.value if after else None,
            detail_json=(
                json.dumps(detail, sort_keys=True, separators=(",", ":"))
                if detail
                else None
            ),
        )

    def propose(
        self,
        data: dict[str, Any],
        *,
        actor: str,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
    ) -> MemoryRecord:
        authorize_memory_action(actor_role, MemoryAction.PROPOSE)
        project_id = str(data.get("project_id") or "")
        repo = self._ensure_repo(project_id)
        prepared = validate_propose_dict(data)
        created = repo.create_record(prepared)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.PROPOSE,
            actor=actor,
            actor_role=actor_role,
            memory_id=created.memory_id,
            before=None,
            after=created,
        )
        return created

    def validate(
        self,
        project_id: str,
        memory_id: str,
        *,
        actor: str,
        actor_role: MemoryActorRole = MemoryActorRole.OS_CONTROL_PLANE,
    ) -> MemoryRecord:
        authorize_memory_action(actor_role, MemoryAction.VALIDATE)
        repo = self._ensure_repo(project_id)
        current = repo.get_record(project_id, memory_id)
        validate_lifecycle_transition(
            current.lifecycle_status, LifecycleStatus.VALIDATED
        )
        now = utc_now_iso()
        updated = replace(
            current,
            lifecycle_status=LifecycleStatus.VALIDATED,
            memory_class=MemoryClass.CANDIDATE,
            validated_at=now,
            updated_at=now,
        )
        stored = repo.update_record(updated, expected_content_hash=current.content_hash)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.VALIDATE,
            actor=actor,
            actor_role=actor_role,
            memory_id=memory_id,
            before=current,
            after=stored,
        )
        return stored

    def approve(
        self,
        project_id: str,
        memory_id: str,
        *,
        approver: str,
        actor: str | None = None,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
    ) -> MemoryRecord:
        authorize_memory_action(actor_role, MemoryAction.APPROVE)
        if not approver or not str(approver).strip():
            raise MemoryValidationError("approver must be non-empty")
        repo = self._ensure_repo(project_id)
        current = repo.get_record(project_id, memory_id)
        validate_lifecycle_transition(
            current.lifecycle_status, LifecycleStatus.APPROVED
        )
        now = utc_now_iso()
        updated = replace(
            current,
            lifecycle_status=LifecycleStatus.APPROVED,
            memory_class=MemoryClass.APPROVED,
            approved_by=approver,
            approval_method=ApprovalMethod.HUMAN,
            approved_at=now,
            updated_at=now,
        )
        stored = repo.update_record(updated, expected_content_hash=current.content_hash)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.APPROVE,
            actor=actor or approver,
            actor_role=actor_role,
            memory_id=memory_id,
            before=current,
            after=stored,
        )
        return stored

    def reject(
        self,
        project_id: str,
        memory_id: str,
        *,
        reason: str,
        actor: str,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
    ) -> MemoryRecord:
        authorize_memory_action(actor_role, MemoryAction.REJECT)
        if not reason or not str(reason).strip():
            raise MemoryValidationError("rejection reason must be non-empty")
        repo = self._ensure_repo(project_id)
        current = repo.get_record(project_id, memory_id)
        validate_lifecycle_transition(
            current.lifecycle_status, LifecycleStatus.REJECTED
        )
        now = utc_now_iso()
        updated = replace(
            current,
            lifecycle_status=LifecycleStatus.REJECTED,
            memory_class=MemoryClass.REJECTED,
            rejection_reason=reason,
            updated_at=now,
        )
        stored = repo.update_record(updated, expected_content_hash=current.content_hash)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.REJECT,
            actor=actor,
            actor_role=actor_role,
            memory_id=memory_id,
            before=current,
            after=stored,
            detail={"reason": reason},
        )
        return stored

    def archive(
        self,
        project_id: str,
        memory_id: str,
        *,
        actor: str,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
    ) -> MemoryRecord:
        authorize_memory_action(actor_role, MemoryAction.ARCHIVE)
        repo = self._ensure_repo(project_id)
        current = repo.get_record(project_id, memory_id)
        validate_lifecycle_transition(
            current.lifecycle_status, LifecycleStatus.ARCHIVED
        )
        now = utc_now_iso()
        updated = replace(
            current,
            lifecycle_status=LifecycleStatus.ARCHIVED,
            memory_class=MemoryClass.ARCHIVED,
            updated_at=now,
        )
        stored = repo.update_record(updated, expected_content_hash=current.content_hash)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.ARCHIVE,
            actor=actor,
            actor_role=actor_role,
            memory_id=memory_id,
            before=current,
            after=stored,
        )
        return stored

    def forget(
        self,
        project_id: str,
        memory_id: str,
        *,
        actor: str,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
    ) -> MemoryRecord:
        authorize_memory_action(actor_role, MemoryAction.FORGET)
        repo = self._ensure_repo(project_id)
        current = repo.get_record(project_id, memory_id)
        validate_lifecycle_transition(
            current.lifecycle_status, LifecycleStatus.FORGOTTEN
        )
        now = utc_now_iso()
        # Forgotten may keep prior class (CLASS_STATUS_PAIRINGS).
        updated = replace(
            current,
            lifecycle_status=LifecycleStatus.FORGOTTEN,
            forgotten_at=now,
            updated_at=now,
        )
        stored = repo.update_record(updated, expected_content_hash=current.content_hash)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.FORGET,
            actor=actor,
            actor_role=actor_role,
            memory_id=memory_id,
            before=current,
            after=stored,
        )
        return stored

    def hard_delete(
        self,
        project_id: str,
        memory_id: str,
        *,
        actor: str,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
    ) -> MemoryRecord:
        """Erase content; keep tombstone + audit. Human only. Prefer forget first."""
        authorize_memory_action(actor_role, MemoryAction.HARD_DELETE)
        repo = self._ensure_repo(project_id)
        current = repo.get_record(project_id, memory_id)
        now = utc_now_iso()
        # Soft-forget first if not already forgotten (legal transition), then erase.
        working = current
        if working.lifecycle_status is not LifecycleStatus.FORGOTTEN:
            validate_lifecycle_transition(
                working.lifecycle_status, LifecycleStatus.FORGOTTEN
            )
            working = replace(
                working,
                lifecycle_status=LifecycleStatus.FORGOTTEN,
                forgotten_at=now,
                updated_at=now,
            )
            working = repo.update_record(
                working, expected_content_hash=current.content_hash
            )
            self._audit(
                repo,
                project_id=project_id,
                action=MemoryAction.FORGET,
                actor=actor,
                actor_role=actor_role,
                memory_id=memory_id,
                before=current,
                after=working,
                detail={"via": "hard_delete"},
            )
        erased = replace(
            working,
            content="",
            content_normalized=working.content_normalized or "",
            content_erased_at=now,
            updated_at=now,
            evidence=(),
        )
        stored = repo.update_record(erased)
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.HARD_DELETE,
            actor=actor,
            actor_role=actor_role,
            memory_id=memory_id,
            before=working,
            after=stored,
        )
        return stored

    def supersede(
        self,
        project_id: str,
        old_memory_id: str,
        *,
        new_content: str,
        actor: str,
        approver: str,
        category: MemoryCategory | None = None,
        title: str | None = None,
        actor_role: MemoryActorRole = MemoryActorRole.HUMAN_OPERATOR,
        proposed_by: str | None = None,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        """Mark old superseded; create and approve a linked replacement."""
        authorize_memory_action(actor_role, MemoryAction.SUPERSEDE)
        if not approver or not str(approver).strip():
            raise MemoryValidationError("approver must be non-empty")
        repo = self._ensure_repo(project_id)
        old = repo.get_record(project_id, old_memory_id)
        if old.lifecycle_status is not LifecycleStatus.APPROVED:
            raise MemoryValidationError(
                "supersede requires an approved source memory"
            )
        validate_lifecycle_transition(
            old.lifecycle_status, LifecycleStatus.SUPERSEDED
        )
        now = utc_now_iso()
        new_id = new_memory_id()
        candidate = prepare_candidate_record(
            MemoryRecord(
                memory_id=new_id,
                project_id=project_id,
                category=category or old.category,
                content=new_content,
                proposed_by=proposed_by or actor,
                source_type=MemorySourceType.OPERATOR,
                title=title if title is not None else old.title,
                sensitivity=old.sensitivity,
                evidence_strength=old.evidence_strength,
                supersedes_memory_id=old_memory_id,
                created_at=now,
                updated_at=now,
            )
        )
        # Fast-path: validated + approved in one operator supersession.
        new_record = replace(
            candidate,
            lifecycle_status=LifecycleStatus.APPROVED,
            memory_class=MemoryClass.APPROVED,
            approved_by=approver,
            approval_method=ApprovalMethod.HUMAN,
            approved_at=now,
            validated_at=now,
            updated_at=now,
        )
        created = repo.create_record(new_record)
        old_updated = replace(
            old,
            lifecycle_status=LifecycleStatus.SUPERSEDED,
            memory_class=MemoryClass.SUPERSEDED,
            superseded_by_memory_id=created.memory_id,
            updated_at=now,
        )
        old_stored = repo.update_record(
            old_updated, expected_content_hash=old.content_hash
        )
        repo.create_link(
            MemoryLink(
                link_id=new_memory_link_id(),
                project_id=project_id,
                from_memory_id=created.memory_id,
                to_memory_id=old_memory_id,
                link_type=LinkType.SUPERSEDES,
                created_at=now,
            ),
            created_by=actor,
        )
        repo.create_link(
            MemoryLink(
                link_id=new_memory_link_id(),
                project_id=project_id,
                from_memory_id=old_memory_id,
                to_memory_id=created.memory_id,
                link_type=LinkType.SUPERSEDED_BY,
                created_at=now,
            ),
            created_by=actor,
        )
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.SUPERSEDE,
            actor=actor,
            actor_role=actor_role,
            memory_id=old_memory_id,
            before=old,
            after=old_stored,
            detail={"new_memory_id": created.memory_id},
        )
        self._audit(
            repo,
            project_id=project_id,
            action=MemoryAction.APPROVE,
            actor=approver,
            actor_role=actor_role,
            memory_id=created.memory_id,
            before=None,
            after=created,
            detail={"via": "supersede", "supersedes": old_memory_id},
        )
        return old_stored, created

    def list_records(
        self,
        project_id: str,
        *,
        lifecycle_status: LifecycleStatus | None = None,
        memory_class: MemoryClass | None = None,
        category: MemoryCategory | None = None,
        limit: int | None = None,
    ) -> tuple[MemoryRecord, ...]:
        repo = self._ensure_repo(project_id)
        return repo.list_records(
            project_id,
            lifecycle_status=lifecycle_status,
            memory_class=memory_class,
            category=category,
            limit=limit,
        )

    def retrieve(
        self,
        project_id: str,
        *,
        limit: int | None = None,
        actor: str = "system",
        actor_role: MemoryActorRole = MemoryActorRole.OS_CONTROL_PLANE,
        audit: bool | None = None,
    ) -> tuple[MemoryRecord, ...]:
        """Return approved memories in deterministic retrieval order."""
        repo = self._ensure_repo(project_id)
        cfg = self._session_config()
        cap = cfg.max_retrieve_limit
        default = cfg.default_retrieve_limit
        effective = default if limit is None else int(limit)
        if effective < 1:
            raise MemoryValidationError("limit must be >= 1")
        if effective > cap:
            raise MemoryValidationError(
                f"limit exceeds max_retrieve_limit ({cap})"
            )
        # Fetch up to cap then sort + slice (ordering differs from list_records).
        raw = repo.list_records(
            project_id,
            lifecycle_status=LifecycleStatus.APPROVED,
            memory_class=MemoryClass.APPROVED,
            limit=cap,
        )
        # Stable multi-key: strength DESC, approved_at DESC, memory_id ASC.
        ordered = sorted(raw, key=lambda r: r.memory_id)
        ordered = sorted(
            ordered, key=lambda r: r.approved_at or "", reverse=True
        )
        ordered = sorted(
            ordered,
            key=lambda r: _EVIDENCE_STRENGTH_RANK.get(r.evidence_strength, 0),
            reverse=True,
        )
        hits = tuple(ordered[:effective])
        do_audit = cfg.audit_retrievals if audit is None else bool(audit)
        if do_audit:
            self._audit(
                repo,
                project_id=project_id,
                action="retrieve",
                actor=actor,
                actor_role=actor_role,
                memory_id=None,
                before=None,
                after=None,
                detail={
                    "count": len(hits),
                    "memory_ids": [h.memory_id for h in hits],
                    "limit": effective,
                },
            )
        return hits

    def get(self, project_id: str, memory_id: str) -> MemoryRecord:
        repo = self._ensure_repo(project_id)
        return repo.get_record(project_id, memory_id)

    def list_events(
        self,
        project_id: str,
        *,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> tuple[dict[str, object], ...]:
        repo = self._ensure_repo(project_id)
        return repo.list_events(project_id, memory_id=memory_id, limit=limit)


def set_project_memory_enabled(
    registry: ProjectRegistry,
    project_id: str,
    enabled: bool,
) -> Any:
    """Persist per-project memory opt-in flag on the registry."""
    record = registry.require(project_id)
    record.memory_enabled = bool(enabled)
    registry.register(record, overwrite=True)
    return record
