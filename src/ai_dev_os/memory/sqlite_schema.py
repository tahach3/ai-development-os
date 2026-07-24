"""SQLite schema helpers for Phase B3.2 (DDL + compatibility checks; no CRUD)."""

from __future__ import annotations

import sqlite3
from enum import Enum
from typing import Iterable

from .domain import (
    ApprovalMethod,
    EvidenceStrength,
    LifecycleStatus,
    LinkType,
    MemoryAction,
    MemoryCategory,
    MemoryClass,
    MemoryEvidenceType,
    MemorySourceType,
    Sensitivity,
)
from .errors import MemoryMigrationError
from .versions import MEMORY_SCHEMA_VERSION

# B2 §10 audit actions beyond B3.1 MemoryAction (retrieve + store-level migrate).
_EXTRA_EVENT_ACTIONS = frozenset({"retrieve", "migrate"})
MEMORY_EVENT_ACTION_VALUES: frozenset[str] = frozenset(
    m.value for m in MemoryAction
) | _EXTRA_EVENT_ACTIONS

MEMORY_ACTOR_KIND_VALUES: frozenset[str] = frozenset({"human", "system", "service"})

REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "schema_migrations",
        "memory_records",
        "memory_evidence",
        "memory_events",
        "memory_links",
    }
)

# Indexes justified for future project-scoped retrieval (B2 §6.3–6.5 / §8).
REQUIRED_INDEXES: frozenset[str] = frozenset(
    {
        "idx_memory_records_project_lifecycle_class",
        "idx_memory_records_project_category",
        "idx_memory_records_project_approved_at",
        "idx_memory_records_project_content_hash",
        "idx_memory_records_task_id",
        "idx_memory_evidence_memory_id",
        "idx_memory_evidence_project_type",
        "idx_memory_events_project_created",
        "idx_memory_events_memory_created",
        "idx_memory_links_project_from",
        "idx_memory_links_project_to",
    }
)


def enum_sql_in_list(enum_cls: type[Enum]) -> str:
    """Build a SQL IN-list from an Enum (single source of truth with B3.1)."""
    return ", ".join(f"'{member.value}'" for member in enum_cls)


def values_sql_in_list(values: Iterable[str]) -> str:
    ordered = sorted(values)
    return ", ".join(f"'{v}'" for v in ordered)


def domain_enum_values(enum_cls: type[Enum]) -> frozenset[str]:
    return frozenset(member.value for member in enum_cls)


def build_initial_schema_sql() -> str:
    """Return deterministic DDL for migration 001 (B2 tables + indexes)."""
    memory_class_in = enum_sql_in_list(MemoryClass)
    lifecycle_in = enum_sql_in_list(LifecycleStatus)
    sensitivity_in = enum_sql_in_list(Sensitivity)
    evidence_strength_in = enum_sql_in_list(EvidenceStrength)
    category_in = enum_sql_in_list(MemoryCategory)
    source_type_in = enum_sql_in_list(MemorySourceType)
    approval_method_in = enum_sql_in_list(ApprovalMethod)
    evidence_type_in = enum_sql_in_list(MemoryEvidenceType)
    link_type_in = enum_sql_in_list(LinkType)
    action_in = values_sql_in_list(MEMORY_EVENT_ACTION_VALUES)
    actor_kind_in = values_sql_in_list(MEMORY_ACTOR_KIND_VALUES)
    schema_ver = MEMORY_SCHEMA_VERSION

    return f"""
CREATE TABLE schema_migrations (
    version TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL,
    CHECK (length(version) > 0),
    CHECK (length(name) > 0),
    CHECK (length(checksum) = 64),
    CHECK (checksum GLOB '[0-9a-f]*'),
    CHECK (length(applied_at) > 0),
    CHECK (length(description) > 0)
);

CREATE TABLE memory_records (
    memory_id TEXT NOT NULL PRIMARY KEY,
    project_id TEXT NOT NULL,
    memory_class TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT,
    content TEXT,
    content_normalized TEXT,
    content_hash TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    evidence_strength TEXT NOT NULL DEFAULT 'none',
    confidence REAL,
    source_type TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    provider_id TEXT,
    task_id TEXT,
    plan_fingerprint TEXT,
    session_id TEXT,
    orchestration_id TEXT,
    approved_by TEXT,
    approval_method TEXT,
    rejection_reason TEXT,
    valid_from TEXT,
    valid_until TEXT,
    supersedes_memory_id TEXT,
    superseded_by_memory_id TEXT,
    forgotten_at TEXT,
    content_erased_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    validated_at TEXT,
    approved_at TEXT,
    schema_version TEXT NOT NULL DEFAULT '{schema_ver}',
    CHECK (length(memory_id) = 16 AND memory_id GLOB 'mem-[0-9a-f]*'),
    CHECK (length(project_id) > 0),
    CHECK (memory_class IN ({memory_class_in})),
    CHECK (lifecycle_status IN ({lifecycle_in})),
    CHECK (category IN ({category_in})),
    CHECK (sensitivity IN ({sensitivity_in})),
    CHECK (evidence_strength IN ({evidence_strength_in})),
    CHECK (source_type IN ({source_type_in})),
    CHECK (length(proposed_by) > 0),
    CHECK (length(content_hash) = 64),
    CHECK (content_hash GLOB '[0-9a-f]*'),
    CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    CHECK (approval_method IS NULL OR approval_method IN ({approval_method_in})),
    CHECK (schema_version = '{schema_ver}'),
    CHECK (length(created_at) > 0),
    CHECK (length(updated_at) > 0),
    CHECK (
        (content IS NOT NULL AND length(content) > 0)
        OR content_erased_at IS NOT NULL
    ),
    CHECK (
        content_normalized IS NULL OR length(content_normalized) > 0
    ),
    CHECK (
        memory_class != 'approved_memory'
        OR (
            approved_by IS NOT NULL
            AND length(approved_by) > 0
            AND approved_at IS NOT NULL
            AND length(approved_at) > 0
            AND approval_method IS NOT NULL
        )
    ),
    CHECK (
        lifecycle_status != 'forgotten'
        OR (forgotten_at IS NOT NULL AND length(forgotten_at) > 0)
    ),
    CHECK (
        lifecycle_status != 'rejected'
        OR (rejection_reason IS NOT NULL AND length(rejection_reason) > 0)
    ),
    UNIQUE (memory_id, project_id)
);

CREATE TABLE memory_evidence (
    evidence_id TEXT NOT NULL PRIMARY KEY,
    memory_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (length(evidence_id) = 17 AND evidence_id GLOB 'evid-[0-9a-f]*'),
    CHECK (length(project_id) > 0),
    CHECK (evidence_type IN ({evidence_type_in})),
    CHECK (length(evidence_ref) > 0),
    CHECK (length(created_at) > 0),
    FOREIGN KEY (memory_id, project_id)
        REFERENCES memory_records (memory_id, project_id)
);

CREATE TABLE memory_events (
    event_id TEXT NOT NULL PRIMARY KEY,
    memory_id TEXT,
    project_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_kind TEXT NOT NULL,
    from_class TEXT,
    to_class TEXT,
    from_status TEXT,
    to_status TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL,
    CHECK (length(event_id) = 16 AND event_id GLOB 'mev-[0-9a-f]*'),
    CHECK (length(project_id) > 0),
    CHECK (action IN ({action_in})),
    CHECK (length(actor) > 0),
    CHECK (actor_kind IN ({actor_kind_in})),
    CHECK (from_class IS NULL OR from_class IN ({memory_class_in})),
    CHECK (to_class IS NULL OR to_class IN ({memory_class_in})),
    CHECK (from_status IS NULL OR from_status IN ({lifecycle_in})),
    CHECK (to_status IS NULL OR to_status IN ({lifecycle_in})),
    CHECK (length(created_at) > 0),
    FOREIGN KEY (memory_id, project_id)
        REFERENCES memory_records (memory_id, project_id)
);

CREATE TABLE memory_links (
    link_id TEXT NOT NULL PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_memory_id TEXT NOT NULL,
    to_memory_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    CHECK (length(link_id) = 16 AND link_id GLOB 'mlk-[0-9a-f]*'),
    CHECK (length(project_id) > 0),
    CHECK (link_type IN ({link_type_in})),
    CHECK (length(created_at) > 0),
    CHECK (length(created_by) > 0),
    CHECK (from_memory_id != to_memory_id),
    UNIQUE (from_memory_id, to_memory_id, link_type),
    FOREIGN KEY (from_memory_id, project_id)
        REFERENCES memory_records (memory_id, project_id),
    FOREIGN KEY (to_memory_id, project_id)
        REFERENCES memory_records (memory_id, project_id)
);

CREATE INDEX idx_memory_records_project_lifecycle_class
    ON memory_records (project_id, lifecycle_status, memory_class);
CREATE INDEX idx_memory_records_project_category
    ON memory_records (project_id, category);
CREATE INDEX idx_memory_records_project_approved_at
    ON memory_records (project_id, approved_at);
CREATE INDEX idx_memory_records_project_content_hash
    ON memory_records (project_id, content_hash);
CREATE INDEX idx_memory_records_task_id
    ON memory_records (task_id) WHERE task_id IS NOT NULL;
CREATE INDEX idx_memory_evidence_memory_id
    ON memory_evidence (memory_id);
CREATE INDEX idx_memory_evidence_project_type
    ON memory_evidence (project_id, evidence_type);
CREATE INDEX idx_memory_events_project_created
    ON memory_events (project_id, created_at);
CREATE INDEX idx_memory_events_memory_created
    ON memory_events (memory_id, created_at);
CREATE INDEX idx_memory_links_project_from
    ON memory_links (project_id, from_memory_id);
CREATE INDEX idx_memory_links_project_to
    ON memory_links (project_id, to_memory_id);
""".strip()


def list_user_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(r[0]) for r in rows}


def list_user_indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def foreign_keys_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    return bool(row and int(row[0]) == 1)


def validate_schema_compatibility(conn: sqlite3.Connection) -> None:
    """Fail closed if required tables/indexes/FK pragma are missing."""
    if not foreign_keys_enabled(conn):
        raise MemoryMigrationError(
            "SQLite foreign_keys pragma is not enabled; refuse schema use."
        )
    tables = list_user_tables(conn)
    missing_tables = REQUIRED_TABLES - tables
    if missing_tables:
        raise MemoryMigrationError(
            f"Memory schema incomplete; missing tables: {sorted(missing_tables)}"
        )
    indexes = list_user_indexes(conn)
    missing_indexes = REQUIRED_INDEXES - indexes
    if missing_indexes:
        raise MemoryMigrationError(
            f"Memory schema incomplete; missing indexes: {sorted(missing_indexes)}"
        )
