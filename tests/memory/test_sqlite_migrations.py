"""Phase B3.2 — migration bootstrap and atomicity tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from ai_dev_os.memory import (
    MEMORY_SCHEMA_VERSION,
    MemoryConfig,
    MemoryMigration,
    MemoryMigrationError,
    checksum_migration_sql,
    initialize_memory_database,
    open_memory_connection,
    validate_memory_database,
)
from ai_dev_os.memory.sqlite_migrations import (
    REGISTERED_MIGRATIONS,
    apply_pending_migrations,
    read_applied_migrations,
    verify_applied_migrations,
)
from ai_dev_os.memory.sqlite_schema import REQUIRED_INDEXES, REQUIRED_TABLES, list_user_tables


def _enabled(path: Path) -> MemoryConfig:
    return MemoryConfig(enabled=True, db_path=str(path))


def test_empty_database_initializes_idempotently(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    cfg = _enabled(path)
    first = initialize_memory_database(path, config=cfg, root=tmp_path)
    second = initialize_memory_database(path, config=cfg, root=tmp_path)
    assert first.applied_migrations == ("001",)
    assert second.applied_migrations == ("001",)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        rows = conn.execute("SELECT version, name, checksum FROM schema_migrations").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "001"
        assert rows[0][1] == "initial_memory_schema"
        assert rows[0][2] == REGISTERED_MIGRATIONS[0].checksum
        assert list_user_tables(conn) >= REQUIRED_TABLES
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert REQUIRED_INDEXES <= indexes
    finally:
        conn.close()


def test_file_persists_across_reopen(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    initialize_memory_database(path, config=_enabled(path), root=tmp_path)
    info = validate_memory_database(path, config=_enabled(path), root=tmp_path)
    assert info.schema_compatibility_version == MEMORY_SCHEMA_VERSION
    assert info.applied_migrations == ("001",)


def test_checksum_stable_and_mismatch_fails(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    initialize_memory_database(path, config=_enabled(path), root=tmp_path)
    expected = checksum_migration_sql(REGISTERED_MIGRATIONS[0].sql)
    assert REGISTERED_MIGRATIONS[0].checksum == expected

    conn = open_memory_connection(path, root=tmp_path)
    try:
        conn.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            ("0" * 64, "001"),
        )
        conn.commit()
        with pytest.raises(MemoryMigrationError, match="checksum"):
            verify_applied_migrations(conn)
    finally:
        conn.close()


def test_unknown_future_migration_fails(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    initialize_memory_database(path, config=_enabled(path), root=tmp_path)
    conn = open_memory_connection(path, root=tmp_path)
    try:
        conn.execute(
            "INSERT INTO schema_migrations "
            "(version, name, checksum, applied_at, description) "
            "VALUES ('999', 'future', ?, '2026-01-01T00:00:00Z', 'future')",
            ("a" * 64,),
        )
        conn.commit()
        with pytest.raises(MemoryMigrationError, match="Unknown future"):
            verify_applied_migrations(conn)
    finally:
        conn.close()


def test_ambiguous_schema_without_history_fails(tmp_path: Path):
    path = tmp_path / "orphan.sqlite3"
    conn = open_memory_connection(path, root=tmp_path, create_parents=True)
    try:
        conn.execute("CREATE TABLE memory_records (memory_id TEXT PRIMARY KEY)")
        conn.commit()
        with pytest.raises(MemoryMigrationError, match="Ambiguous"):
            verify_applied_migrations(conn)
    finally:
        conn.close()


def test_failed_migration_rolls_back(tmp_path: Path):
    path = tmp_path / "rollback.sqlite3"
    conn = open_memory_connection(path, root=tmp_path, create_parents=True)
    bad = MemoryMigration(
        version="001",
        name="broken",
        description="broken",
        sql="CREATE TABLE temp_ok (id TEXT); CREATE TABLE !!!invalid;",
    )
    try:
        with pytest.raises(MemoryMigrationError, match="rolled back"):
            apply_pending_migrations(conn, registered=(bad,))
        tables = list_user_tables(conn)
        assert "temp_ok" not in tables
        assert "schema_migrations" not in tables
        assert read_applied_migrations(conn) == {}
    finally:
        conn.close()


def test_no_destructive_downgrade_api():
    # Forward-only registry: no downgrade helpers exported.
    import ai_dev_os.memory.sqlite_migrations as mig

    assert not hasattr(mig, "downgrade")
    assert not hasattr(mig, "rollback_migration")
