"""Phase B3.2 — repository CRUD, disabled guard, deterministic list order."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai_dev_os.memory import (
    DEFAULT_MEMORY_CONFIG,
    MEMORY_SCHEMA_VERSION,
    EvidenceStrength,
    LifecycleStatus,
    LinkType,
    MemoryCategory,
    MemoryClass,
    MemoryConfig,
    MemoryConflictError,
    MemoryDisabledError,
    MemoryEvidenceRef,
    MemoryEvidenceType,
    MemoryLink,
    MemoryNotFoundError,
    MemoryRecord,
    MemorySourceType,
    Sensitivity,
    SqliteMemoryRepository,
    initialize_memory_database,
    new_memory_evidence_id,
    new_memory_id,
    new_memory_link_id,
    prepare_candidate_record,
)


def _enabled(path: Path) -> MemoryConfig:
    return MemoryConfig(enabled=True, db_path=str(path))


def _boot(tmp_path: Path) -> tuple[Path, SqliteMemoryRepository]:
    path = tmp_path / "memory.sqlite3"
    initialize_memory_database(path, config=_enabled(path), root=tmp_path)
    repo = SqliteMemoryRepository(str(path), config=_enabled(path), root=str(tmp_path))
    return path, repo


def _candidate(
    *,
    project_id: str = "demo-project",
    content: str = "Calculator uses NFKC rules",
    created_at: str = "2026-01-01T00:00:00+00:00",
    memory_id: str | None = None,
    evidence: tuple[MemoryEvidenceRef, ...] = (),
) -> MemoryRecord:
    raw = MemoryRecord(
        memory_id=memory_id or new_memory_id(),
        project_id=project_id,
        category=MemoryCategory.PROJECT_FACT,
        content=content,
        proposed_by="operator:alice",
        source_type=MemorySourceType.OPERATOR,
        title="Calc fact",
        sensitivity=Sensitivity.INTERNAL,
        evidence_strength=EvidenceStrength.NONE,
        memory_class=MemoryClass.CANDIDATE,
        lifecycle_status=LifecycleStatus.PROPOSED,
        created_at=created_at,
        updated_at=created_at,
        evidence=evidence,
    )
    return prepare_candidate_record(raw)


def test_disabled_repository_construction_refuses():
    with pytest.raises(MemoryDisabledError):
        SqliteMemoryRepository(
            "workspace/memory/memory.sqlite3",
            config=DEFAULT_MEMORY_CONFIG,
        )


def test_disabled_initialize_refuses_typed(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    with pytest.raises(MemoryDisabledError):
        initialize_memory_database(path, root=tmp_path, config=DEFAULT_MEMORY_CONFIG)
    assert not path.exists()


def test_create_read_update_round_trip_hash_integrity(tmp_path: Path):
    _, repo = _boot(tmp_path)
    evid = MemoryEvidenceRef(
        evidence_id=new_memory_evidence_id(),
        evidence_type=MemoryEvidenceType.OPERATOR_NOTE,
        evidence_ref="note-1",
    )
    created = repo.create_record(_candidate(evidence=(evid,)))
    assert created.content_hash
    assert len(created.content_hash) == 64
    assert created.schema_version == MEMORY_SCHEMA_VERSION
    assert created.content_normalized == "calculator uses nfkc rules"
    assert len(created.evidence) == 1

    loaded = repo.get_record(created.project_id, created.memory_id)
    assert loaded.content_hash == created.content_hash
    assert loaded.content_normalized == created.content_normalized
    assert loaded.evidence[0].evidence_ref == "note-1"

    updated_raw = replace(
        loaded,
        lifecycle_status=LifecycleStatus.VALIDATED,
        validated_at="2026-01-01T01:00:00+00:00",
        updated_at="2026-01-01T01:00:00+00:00",
    )
    # Optimistic check uses stored hash; repository recomputes hash for new status.
    updated = repo.update_record(
        updated_raw, expected_content_hash=created.content_hash
    )
    assert updated.lifecycle_status is LifecycleStatus.VALIDATED
    assert updated.content_hash != created.content_hash
    assert len(updated.content_hash) == 64

    with pytest.raises(MemoryConflictError):
        repo.update_record(updated, expected_content_hash="0" * 64)


def test_list_order_deterministic_not_wall_clock(tmp_path: Path):
    _, repo = _boot(tmp_path)
    # Insert with later created_at first, earlier second — list must sort by created_at.
    later = repo.create_record(
        _candidate(
            content="Later fact AAA",
            created_at="2026-01-02T00:00:00+00:00",
            memory_id="mem-bbbbbbbbbbbb",
        )
    )
    earlier = repo.create_record(
        _candidate(
            content="Earlier fact BBB",
            created_at="2026-01-01T00:00:00+00:00",
            memory_id="mem-aaaaaaaaaaaa",
        )
    )
    listed = repo.list_records("demo-project")
    assert [r.memory_id for r in listed] == [earlier.memory_id, later.memory_id]
    # Same timestamp: secondary key memory_id ASC
    same_a = repo.create_record(
        _candidate(
            project_id="p2",
            content="Same stamp A",
            created_at="2026-03-01T00:00:00+00:00",
            memory_id="mem-cccccccccccc",
        )
    )
    same_b = repo.create_record(
        _candidate(
            project_id="p2",
            content="Same stamp B",
            created_at="2026-03-01T00:00:00+00:00",
            memory_id="mem-dddddddddddd",
        )
    )
    listed2 = repo.list_records("p2")
    assert [r.memory_id for r in listed2] == [same_a.memory_id, same_b.memory_id]


def test_project_scope_miss_is_not_found(tmp_path: Path):
    _, repo = _boot(tmp_path)
    rec = repo.create_record(_candidate(project_id="proj-a"))
    with pytest.raises(MemoryNotFoundError):
        repo.get_record("proj-b", rec.memory_id)


def test_link_round_trip(tmp_path: Path):
    _, repo = _boot(tmp_path)
    a = repo.create_record(_candidate(content="Link endpoint A"))
    b = repo.create_record(_candidate(content="Link endpoint B"))
    link = repo.create_link(
        MemoryLink(
            link_id=new_memory_link_id(),
            project_id="demo-project",
            from_memory_id=a.memory_id,
            to_memory_id=b.memory_id,
            link_type=LinkType.RELATED,
            created_at="2026-01-01T00:00:00+00:00",
        ),
        created_by="operator:alice",
    )
    links = repo.list_links("demo-project", memory_id=a.memory_id)
    assert len(links) == 1
    assert links[0].link_id == link.link_id
    assert links[0].link_type is LinkType.RELATED


def test_memory_status_cli_reports_disabled(capsys):
    from ai_dev_os.cli import cmd_memory_status

    class _Args:
        pass

    rc = cmd_memory_status(_Args())
    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "disabled"' in out
    assert '"enabled": false' in out
