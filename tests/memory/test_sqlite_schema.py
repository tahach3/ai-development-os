"""Phase B3.2 — schema constraints, isolation, security, B3.1 compatibility."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from ai_dev_os.memory import (
    MEMORY_EVENT_ACTION_VALUES,
    MEMORY_SCHEMA_VERSION,
    ApprovalMethod,
    EvidenceStrength,
    LifecycleStatus,
    LinkType,
    MemoryAction,
    MemoryCategory,
    MemoryClass,
    MemoryConfig,
    MemoryEvidenceType,
    MemorySourceType,
    Sensitivity,
    domain_enum_values,
    initialize_memory_database,
    new_memory_evidence_id,
    new_memory_event_id,
    new_memory_id,
    new_memory_link_id,
    open_memory_connection,
)
from ai_dev_os.memory.sqlite_schema import enum_sql_in_list
from ai_dev_os.models import utc_now_iso

HASH_A = "a" * 64
HASH_B = "b" * 64


def _cfg(path: Path) -> MemoryConfig:
    return MemoryConfig(enabled=True, db_path=str(path))


def _boot(tmp_path: Path) -> Path:
    path = tmp_path / "memory.sqlite3"
    initialize_memory_database(path, config=_cfg(path), root=tmp_path)
    return path


def _insert_record(
    conn: sqlite3.Connection,
    *,
    memory_id: str,
    project_id: str,
    content: str = "hello world",
    content_hash: str = HASH_A,
    memory_class: str = MemoryClass.CANDIDATE.value,
    lifecycle_status: str = LifecycleStatus.PROPOSED.value,
    approved_by: str | None = None,
    approved_at: str | None = None,
    approval_method: str | None = None,
    rejection_reason: str | None = None,
    forgotten_at: str | None = None,
    content_erased_at: str | None = None,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO memory_records (
            memory_id, project_id, memory_class, lifecycle_status, category,
            content, content_normalized, content_hash, sensitivity, evidence_strength,
            source_type, proposed_by, approved_by, approval_method, rejection_reason,
            forgotten_at, content_erased_at, created_at, updated_at, approved_at,
            schema_version
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?
        )
        """,
        (
            memory_id,
            project_id,
            memory_class,
            lifecycle_status,
            MemoryCategory.PROJECT_FACT.value,
            content,
            content.lower() if content else None,
            content_hash,
            Sensitivity.INTERNAL.value,
            EvidenceStrength.NONE.value,
            MemorySourceType.OPERATOR.value,
            "operator:test",
            approved_by,
            approval_method,
            rejection_reason,
            forgotten_at,
            content_erased_at,
            now,
            now,
            approved_at,
            MEMORY_SCHEMA_VERSION,
        ),
    )


def test_schema_enum_compatibility_with_b3_1():
    assert domain_enum_values(MemoryClass) == {
        "candidate_memory",
        "approved_memory",
        "rejected_memory",
        "superseded_memory",
        "archived_memory",
    }
    for enum_cls in (
        MemoryClass,
        LifecycleStatus,
        Sensitivity,
        EvidenceStrength,
        MemoryCategory,
        MemorySourceType,
        ApprovalMethod,
        LinkType,
        MemoryEvidenceType,
    ):
        sql_list = enum_sql_in_list(enum_cls)
        for value in domain_enum_values(enum_cls):
            assert f"'{value}'" in sql_list
    for action in MemoryAction:
        assert action.value in MEMORY_EVENT_ACTION_VALUES
    assert "retrieve" in MEMORY_EVENT_ACTION_VALUES
    assert "migrate" in MEMORY_EVENT_ACTION_VALUES


def test_valid_and_invalid_enums(tmp_path: Path):
    path = _boot(tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        mid = new_memory_id()
        _insert_record(conn, memory_id=mid, project_id="proj-a")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_record(
                conn,
                memory_id=new_memory_id(),
                project_id="proj-a",
                content_hash=HASH_B,
                memory_class="not_a_class",
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_content_and_hash_constraints(tmp_path: Path):
    path = _boot(tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_record(
                conn,
                memory_id=new_memory_id(),
                project_id="proj-a",
                content="",
            )
            conn.commit()
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_record(
                conn,
                memory_id=new_memory_id(),
                project_id="proj-a",
                content_hash="deadbeef",
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_approved_requires_approver(tmp_path: Path):
    path = _boot(tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_record(
                conn,
                memory_id=new_memory_id(),
                project_id="proj-a",
                memory_class=MemoryClass.APPROVED.value,
                lifecycle_status=LifecycleStatus.APPROVED.value,
            )
            conn.commit()
        conn.rollback()
        _insert_record(
            conn,
            memory_id=new_memory_id(),
            project_id="proj-a",
            memory_class=MemoryClass.APPROVED.value,
            lifecycle_status=LifecycleStatus.APPROVED.value,
            approved_by="operator:alice",
            approved_at=utc_now_iso(),
            approval_method=ApprovalMethod.HUMAN.value,
            content_hash=HASH_B,
        )
        conn.commit()
    finally:
        conn.close()


def test_content_hash_not_globally_unique(tmp_path: Path):
    path = _boot(tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        _insert_record(conn, memory_id=new_memory_id(), project_id="proj-a", content_hash=HASH_A)
        _insert_record(conn, memory_id=new_memory_id(), project_id="proj-b", content_hash=HASH_A)
        conn.commit()
    finally:
        conn.close()


def test_project_isolation_evidence_events_links(tmp_path: Path):
    path = _boot(tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        a = new_memory_id()
        b = new_memory_id()
        _insert_record(conn, memory_id=a, project_id="proj-a")
        _insert_record(conn, memory_id=b, project_id="proj-b", content_hash=HASH_B)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memory_evidence "
                "(evidence_id, memory_id, project_id, evidence_type, evidence_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    new_memory_evidence_id(),
                    a,
                    "proj-b",
                    MemoryEvidenceType.OPERATOR_NOTE.value,
                    "note-1",
                    utc_now_iso(),
                ),
            )
            conn.commit()
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memory_events "
                "(event_id, memory_id, project_id, action, actor, actor_kind, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_memory_event_id(),
                    a,
                    "proj-b",
                    MemoryAction.PROPOSE.value,
                    "operator:test",
                    "human",
                    utc_now_iso(),
                ),
            )
            conn.commit()
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memory_links "
                "(link_id, project_id, from_memory_id, to_memory_id, link_type, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_memory_link_id(),
                    "proj-a",
                    a,
                    b,
                    LinkType.RELATED.value,
                    utc_now_iso(),
                    "operator:test",
                ),
            )
            conn.commit()
        conn.rollback()

        # Same-project link OK
        c = new_memory_id()
        _insert_record(conn, memory_id=c, project_id="proj-a", content_hash=HASH_B)
        conn.execute(
            "INSERT INTO memory_links "
            "(link_id, project_id, from_memory_id, to_memory_id, link_type, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_memory_link_id(),
                "proj-a",
                a,
                c,
                LinkType.RELATED.value,
                utc_now_iso(),
                "operator:test",
            ),
        )
        conn.execute(
            "INSERT INTO memory_evidence "
            "(evidence_id, memory_id, project_id, evidence_type, evidence_ref, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_memory_evidence_id(),
                a,
                "proj-a",
                MemoryEvidenceType.OPERATOR_NOTE.value,
                "note-ok",
                utc_now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_parameter_binding_resists_injection(tmp_path: Path):
    path = _boot(tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        evil = "proj-a'; DROP TABLE memory_records;--"
        with pytest.raises(sqlite3.IntegrityError):
            # Invalid memory_id format / FK â€” still bound as data, tables remain.
            conn.execute(
                "INSERT INTO memory_evidence "
                "(evidence_id, memory_id, project_id, evidence_type, evidence_ref, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    new_memory_evidence_id(),
                    new_memory_id(),
                    evil,
                    MemoryEvidenceType.OTHER.value,
                    "x",
                    utc_now_iso(),
                ),
            )
            conn.commit()
        conn.rollback()
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "memory_records" in tables
    finally:
        conn.close()


def test_package_version_independent_of_schema():
    import ai_dev_os

    # Package version may move with unrelated rounds; memory schema stays memory.1.
    assert ai_dev_os.__version__
    assert MEMORY_SCHEMA_VERSION == "memory.1"
    assert not str(ai_dev_os.__version__).startswith("memory.")


def test_b3_1_hash_behavior_unchanged():
    from ai_dev_os.memory import (
        build_memory_fingerprint_payload,
        compute_content_hash,
        normalize_memory_content,
    )

    assert normalize_memory_content("  AbC  Def ") == "abc def"
    payload = build_memory_fingerprint_payload(
        project_id="p",
        category="project_fact",
        content_normalized="abc",
        sensitivity="internal",
        memory_class="candidate_memory",
        lifecycle_status="proposed",
        evidence_strength="none",
        source_type="operator",
        proposed_by="op",
    )
    h1 = compute_content_hash(payload)
    h2 = compute_content_hash(payload)
    assert h1 == h2
    assert len(h1) == 64
