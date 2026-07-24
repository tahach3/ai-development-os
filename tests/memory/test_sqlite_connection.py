"""Phase B3.2 — SQLite connection and path-safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dev_os.memory import (
    DEFAULT_MEMORY_CONFIG,
    MemoryConfig,
    MemoryDisabledError,
    MemoryPersistenceError,
    initialize_memory_database,
    memory_connection,
    open_memory_connection,
    validate_memory_db_path,
)


def test_import_does_not_create_database(tmp_path: Path):
    target = tmp_path / "workspace" / "memory" / "memory.sqlite3"
    assert not target.exists()
    import ai_dev_os.memory as memory_mod

    assert memory_mod.DEFAULT_MEMORY_CONFIG.enabled is False
    assert not target.exists()


def test_disabled_config_refuses_initialize(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    with pytest.raises(MemoryDisabledError):
        initialize_memory_database(path, root=tmp_path, config=DEFAULT_MEMORY_CONFIG)
    assert not path.exists()


def test_file_backed_connection_pragmas(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    with memory_connection(path, root=tmp_path, create_parents=True) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
    # closed deterministically
    with pytest.raises(Exception):
        conn.execute("SELECT 1")


def test_in_memory_skips_wal_requirement():
    conn = open_memory_connection(":memory:")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        assert mode in {"memory", "delete", "off"}
    finally:
        conn.close()


def test_invalid_paths_rejected(tmp_path: Path):
    with pytest.raises(MemoryPersistenceError):
        validate_memory_db_path("")
    with pytest.raises(MemoryPersistenceError):
        validate_memory_db_path("file:mem.db?mode=memory")
    with pytest.raises(MemoryPersistenceError):
        validate_memory_db_path(tmp_path)  # directory
    with pytest.raises(MemoryPersistenceError):
        validate_memory_db_path("relative/without/root.sqlite3")
    outside = Path.cwd() / "not-under-tmp.sqlite3"
    with pytest.raises(MemoryPersistenceError):
        validate_memory_db_path(outside.resolve(), root=tmp_path)


def test_traversal_containment_rejected(tmp_path: Path):
    with pytest.raises(MemoryPersistenceError):
        validate_memory_db_path("../escape.sqlite3", root=tmp_path)


def test_parent_not_created_without_flag(tmp_path: Path):
    path = tmp_path / "nested" / "memory.sqlite3"
    with pytest.raises(MemoryPersistenceError):
        open_memory_connection(path, root=tmp_path, create_parents=False)
    assert not path.exists()


def test_enabled_initialize_creates_file(tmp_path: Path):
    path = tmp_path / "memory.sqlite3"
    cfg = MemoryConfig(enabled=True, db_path=str(path))
    info = initialize_memory_database(path, config=cfg, root=tmp_path)
    assert path.exists()
    assert info.applied_migrations == ("001",)
    assert info.schema_compatibility_version == "memory.1"
