"""SQLite repository for immutable B3.1 memory models (Phase B3.2)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Sequence

from ai_dev_os.models import utc_now_iso

from .config import DEFAULT_MEMORY_CONFIG, MemoryConfig
from .domain import (
    ApprovalMethod,
    EvidenceStrength,
    LifecycleStatus,
    LinkType,
    MemoryCategory,
    MemoryClass,
    MemoryEvidenceRef,
    MemoryEvidenceType,
    MemoryLink,
    MemoryRecord,
    MemorySourceType,
    Sensitivity,
    is_valid_memory_id,
    new_memory_link_id,
)
from .errors import (
    MemoryConflictError,
    MemoryDisabledError,
    MemoryNotFoundError,
    MemoryPersistenceError,
    MemoryValidationError,
)
from .hashing import compute_content_hash
from .normalization import normalize_memory_content
from .sqlite_connection import open_memory_connection
from .validation import (
    validate_content_hash,
    validate_evidence_ref,
    validate_memory_record_fields,
)
from .versions import MEMORY_SCHEMA_VERSION

_RECORD_COLUMNS = (
    "memory_id",
    "project_id",
    "memory_class",
    "lifecycle_status",
    "category",
    "title",
    "content",
    "content_normalized",
    "content_hash",
    "sensitivity",
    "evidence_strength",
    "confidence",
    "source_type",
    "proposed_by",
    "provider_id",
    "task_id",
    "plan_fingerprint",
    "session_id",
    "orchestration_id",
    "approved_by",
    "approval_method",
    "rejection_reason",
    "valid_from",
    "valid_until",
    "supersedes_memory_id",
    "superseded_by_memory_id",
    "forgotten_at",
    "content_erased_at",
    "created_at",
    "updated_at",
    "validated_at",
    "approved_at",
    "schema_version",
)


class SqliteMemoryRepository:
    """Project-scoped CRUD over ``MemoryRecord`` using stdlib sqlite3 only.

    Construction and every operation require ``config.enabled=True``.
    Disabled (default) → typed ``MemoryDisabledError`` (never silent no-op).
    """

    def __init__(
        self,
        path: str,
        *,
        config: MemoryConfig | None = None,
        root: str | None = None,
    ) -> None:
        self._config = config if config is not None else DEFAULT_MEMORY_CONFIG
        self._guard_enabled()
        if self._config.backend != "sqlite":
            raise MemoryPersistenceError(
                f"Unsupported memory backend: {self._config.backend}"
            )
        self._path = path
        self._root = root

    def _guard_enabled(self) -> None:
        if not self._config.enabled:
            raise MemoryDisabledError(
                "Shared memory is disabled; refusing repository access"
            )

    def _connect(self) -> sqlite3.Connection:
        self._guard_enabled()
        return open_memory_connection(
            self._path,
            busy_timeout_ms=self._config.busy_timeout_ms,
            root=self._root,
            create_parents=False,
        )

    def create_record(self, record: MemoryRecord) -> MemoryRecord:
        """Insert a validated record + evidence; return the stored model."""
        prepared = self._prepare_for_persist(record)
        conn = self._connect()
        try:
            self._insert_record_row(conn, prepared)
            self._replace_evidence(conn, prepared)
            conn.commit()
            return self._load_record(conn, prepared.project_id, prepared.memory_id)
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise MemoryConflictError(
                "Memory create refused by database constraints"
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_record(self, project_id: str, memory_id: str) -> MemoryRecord:
        if not project_id or not str(project_id).strip():
            raise MemoryValidationError("project_id must be non-empty")
        if not is_valid_memory_id(memory_id):
            raise MemoryValidationError(f"Invalid memory_id format: {memory_id!r}")
        conn = self._connect()
        try:
            return self._load_record(conn, project_id, memory_id)
        finally:
            conn.close()

    def update_record(
        self,
        record: MemoryRecord,
        *,
        expected_content_hash: str | None = None,
    ) -> MemoryRecord:
        """Update an existing row; optional optimistic content_hash check."""
        prepared = self._prepare_for_persist(record)
        conn = self._connect()
        try:
            existing = self._load_record(conn, prepared.project_id, prepared.memory_id)
            if expected_content_hash is not None:
                if existing.content_hash != expected_content_hash:
                    raise MemoryConflictError(
                        "content_hash mismatch (stale or tampered candidate)"
                    )
            self._update_record_row(conn, prepared)
            self._replace_evidence(conn, prepared)
            conn.commit()
            return self._load_record(conn, prepared.project_id, prepared.memory_id)
        except MemoryConflictError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise MemoryConflictError(
                "Memory update refused by database constraints"
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_records(
        self,
        project_id: str,
        *,
        lifecycle_status: LifecycleStatus | None = None,
        memory_class: MemoryClass | None = None,
        category: MemoryCategory | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[MemoryRecord, ...]:
        """List project-scoped records in deterministic order (created_at, memory_id)."""
        if not project_id or not str(project_id).strip():
            raise MemoryValidationError("project_id must be non-empty")
        if offset < 0:
            raise MemoryValidationError("offset must be non-negative")
        cap = self._config.max_retrieve_limit
        default = self._config.default_retrieve_limit
        effective_limit = default if limit is None else int(limit)
        if effective_limit < 1:
            raise MemoryValidationError("limit must be >= 1")
        if effective_limit > cap:
            raise MemoryValidationError(
                f"limit exceeds max_retrieve_limit ({cap})"
            )

        clauses = ["project_id = ?"]
        params: list[object] = [project_id]
        if lifecycle_status is not None:
            clauses.append("lifecycle_status = ?")
            params.append(lifecycle_status.value)
        if memory_class is not None:
            clauses.append("memory_class = ?")
            params.append(memory_class.value)
        if category is not None:
            clauses.append("category = ?")
            params.append(category.value)
        where = " AND ".join(clauses)
        cols = ", ".join(_RECORD_COLUMNS)
        sql = (
            f"SELECT {cols} FROM memory_records WHERE {where} "
            "ORDER BY created_at ASC, memory_id ASC LIMIT ? OFFSET ?"
        )
        params.extend([effective_limit, offset])

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            out: list[MemoryRecord] = []
            for row in rows:
                mid = str(row["memory_id"])
                evidence = self._load_evidence(conn, project_id, mid)
                out.append(self._row_to_record(row, evidence))
            return tuple(out)
        finally:
            conn.close()

    def create_link(self, link: MemoryLink, *, created_by: str | None = None) -> MemoryLink:
        actor = created_by or "system"
        if not actor or not str(actor).strip():
            raise MemoryValidationError("created_by must be non-empty")
        if link.from_memory_id == link.to_memory_id:
            raise MemoryValidationError("link endpoints must differ")
        conn = self._connect()
        try:
            # Ensure both endpoints exist in project scope.
            self._load_record(conn, link.project_id, link.from_memory_id)
            self._load_record(conn, link.project_id, link.to_memory_id)
            link_id = link.link_id or new_memory_link_id()
            created_at = link.created_at or utc_now_iso()
            conn.execute(
                "INSERT INTO memory_links "
                "(link_id, project_id, from_memory_id, to_memory_id, link_type, "
                "created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    link_id,
                    link.project_id,
                    link.from_memory_id,
                    link.to_memory_id,
                    link.link_type.value,
                    created_at,
                    actor,
                ),
            )
            conn.commit()
            return MemoryLink(
                link_id=link_id,
                project_id=link.project_id,
                from_memory_id=link.from_memory_id,
                to_memory_id=link.to_memory_id,
                link_type=link.link_type,
                created_at=created_at,
            )
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise MemoryConflictError(
                "Memory link create refused by database constraints"
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_links(
        self,
        project_id: str,
        *,
        memory_id: str | None = None,
    ) -> tuple[MemoryLink, ...]:
        if not project_id or not str(project_id).strip():
            raise MemoryValidationError("project_id must be non-empty")
        clauses = ["project_id = ?"]
        params: list[object] = [project_id]
        if memory_id is not None:
            if not is_valid_memory_id(memory_id):
                raise MemoryValidationError(f"Invalid memory_id format: {memory_id!r}")
            clauses.append("(from_memory_id = ? OR to_memory_id = ?)")
            params.extend([memory_id, memory_id])
        where = " AND ".join(clauses)
        sql = (
            "SELECT link_id, project_id, from_memory_id, to_memory_id, link_type, "
            f"created_at FROM memory_links WHERE {where} "
            "ORDER BY created_at ASC, link_id ASC"
        )
        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return tuple(
                MemoryLink(
                    link_id=str(r["link_id"]),
                    project_id=str(r["project_id"]),
                    from_memory_id=str(r["from_memory_id"]),
                    to_memory_id=str(r["to_memory_id"]),
                    link_type=LinkType(str(r["link_type"])),
                    created_at=str(r["created_at"]),
                )
                for r in rows
            )
        finally:
            conn.close()

    def _prepare_for_persist(self, record: MemoryRecord) -> MemoryRecord:
        self._guard_enabled()
        validate_memory_record_fields(record)
        content = record.content
        erased = bool(record.content_erased_at)
        if erased:
            # Hard-delete tombstone: content may be empty in the domain model.
            normalized = record.content_normalized
            content_hash = record.content_hash
            if not content_hash:
                raise MemoryValidationError(
                    "content_hash required after content erasure"
                )
            prepared = replace(
                record,
                content=content if content is not None else "",
                content_normalized=normalized,
                schema_version=MEMORY_SCHEMA_VERSION,
            )
        else:
            if not content or not str(content).strip():
                raise MemoryValidationError("content must be non-empty before erase")
            normalized = record.content_normalized or normalize_memory_content(content)
            interim = replace(
                record,
                content_normalized=normalized,
                schema_version=MEMORY_SCHEMA_VERSION,
            )
            # Fingerprint includes class/lifecycle — recompute hash so status
            # transitions stay consistent with B3.1 hashing contracts.
            content_hash = compute_content_hash(interim)
            prepared = replace(interim, content_hash=content_hash)
            validate_content_hash(prepared)
        for ev in prepared.evidence:
            validate_evidence_ref(ev)
        if prepared.schema_version != MEMORY_SCHEMA_VERSION:
            raise MemoryValidationError(
                f"Unsupported memory schema_version: {prepared.schema_version}"
            )
        return prepared

    def _insert_record_row(self, conn: sqlite3.Connection, record: MemoryRecord) -> None:
        placeholders = ", ".join("?" for _ in _RECORD_COLUMNS)
        cols = ", ".join(_RECORD_COLUMNS)
        conn.execute(
            f"INSERT INTO memory_records ({cols}) VALUES ({placeholders})",
            self._record_to_params(record),
        )

    def _update_record_row(self, conn: sqlite3.Connection, record: MemoryRecord) -> None:
        # Do not overwrite created_at; always bump updated_at if caller left it stale.
        assignments = ", ".join(
            f"{c} = ?" for c in _RECORD_COLUMNS if c not in {"memory_id", "project_id", "created_at"}
        )
        params = [
            self._field_value(record, c)
            for c in _RECORD_COLUMNS
            if c not in {"memory_id", "project_id", "created_at"}
        ]
        params.extend([record.memory_id, record.project_id])
        cur = conn.execute(
            f"UPDATE memory_records SET {assignments} "
            "WHERE memory_id = ? AND project_id = ?",
            params,
        )
        if cur.rowcount != 1:
            raise MemoryNotFoundError(
                f"Memory not found: {record.memory_id} in project {record.project_id}"
            )

    def _replace_evidence(self, conn: sqlite3.Connection, record: MemoryRecord) -> None:
        conn.execute(
            "DELETE FROM memory_evidence WHERE memory_id = ? AND project_id = ?",
            (record.memory_id, record.project_id),
        )
        now = utc_now_iso()
        for ev in record.evidence:
            conn.execute(
                "INSERT INTO memory_evidence "
                "(evidence_id, memory_id, project_id, evidence_type, evidence_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ev.evidence_id,
                    record.memory_id,
                    record.project_id,
                    ev.evidence_type.value,
                    ev.evidence_ref,
                    now,
                ),
            )

    def _load_record(
        self, conn: sqlite3.Connection, project_id: str, memory_id: str
    ) -> MemoryRecord:
        cols = ", ".join(_RECORD_COLUMNS)
        row = conn.execute(
            f"SELECT {cols} FROM memory_records "
            "WHERE memory_id = ? AND project_id = ?",
            (memory_id, project_id),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError(
                f"Memory not found: {memory_id} in project {project_id}"
            )
        evidence = self._load_evidence(conn, project_id, memory_id)
        return self._row_to_record(row, evidence)

    def _load_evidence(
        self, conn: sqlite3.Connection, project_id: str, memory_id: str
    ) -> tuple[MemoryEvidenceRef, ...]:
        rows = conn.execute(
            "SELECT evidence_id, evidence_type, evidence_ref FROM memory_evidence "
            "WHERE memory_id = ? AND project_id = ? "
            "ORDER BY evidence_type ASC, evidence_ref ASC, evidence_id ASC",
            (memory_id, project_id),
        ).fetchall()
        return tuple(
            MemoryEvidenceRef(
                evidence_id=str(r["evidence_id"]),
                evidence_type=MemoryEvidenceType(str(r["evidence_type"])),
                evidence_ref=str(r["evidence_ref"]),
                note=None,
            )
            for r in rows
        )

    def _row_to_record(
        self, row: sqlite3.Row, evidence: Sequence[MemoryEvidenceRef]
    ) -> MemoryRecord:
        approval_raw = row["approval_method"]
        content = row["content"]
        return MemoryRecord(
            memory_id=str(row["memory_id"]),
            project_id=str(row["project_id"]),
            memory_class=MemoryClass(str(row["memory_class"])),
            lifecycle_status=LifecycleStatus(str(row["lifecycle_status"])),
            category=MemoryCategory(str(row["category"])),
            title=row["title"],
            content="" if content is None else str(content),
            content_normalized=row["content_normalized"],
            content_hash=str(row["content_hash"]),
            sensitivity=Sensitivity(str(row["sensitivity"])),
            evidence_strength=EvidenceStrength(str(row["evidence_strength"])),
            confidence=row["confidence"],
            source_type=MemorySourceType(str(row["source_type"])),
            proposed_by=str(row["proposed_by"]),
            provider_id=row["provider_id"],
            task_id=row["task_id"],
            plan_fingerprint=row["plan_fingerprint"],
            session_id=row["session_id"],
            orchestration_id=row["orchestration_id"],
            approved_by=row["approved_by"],
            approval_method=(
                ApprovalMethod(str(approval_raw)) if approval_raw else None
            ),
            rejection_reason=row["rejection_reason"],
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            supersedes_memory_id=row["supersedes_memory_id"],
            superseded_by_memory_id=row["superseded_by_memory_id"],
            forgotten_at=row["forgotten_at"],
            content_erased_at=row["content_erased_at"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            validated_at=row["validated_at"],
            approved_at=row["approved_at"],
            schema_version=str(row["schema_version"]),
            evidence=tuple(evidence),
        )

    def _record_to_params(self, record: MemoryRecord) -> tuple[object, ...]:
        return tuple(self._field_value(record, c) for c in _RECORD_COLUMNS)

    def _field_value(self, record: MemoryRecord, column: str) -> object:
        if column == "memory_class":
            return record.memory_class.value
        if column == "lifecycle_status":
            return record.lifecycle_status.value
        if column == "category":
            return record.category.value
        if column == "sensitivity":
            return record.sensitivity.value
        if column == "evidence_strength":
            return record.evidence_strength.value
        if column == "source_type":
            return record.source_type.value
        if column == "approval_method":
            return record.approval_method.value if record.approval_method else None
        if column == "content":
            if record.content_erased_at and (not record.content or not record.content.strip()):
                return None
            return record.content
        if column == "schema_version":
            return record.schema_version or MEMORY_SCHEMA_VERSION
        return getattr(record, column)
