"""SQLite connection factory and path safety for shared memory (Phase B3.2)."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ai_dev_os.validation import is_path_under

from .config import DEFAULT_MEMORY_CONFIG, MemoryConfig
from .errors import MemoryDisabledError, MemoryMigrationError, MemoryPersistenceError
from .sqlite_migrations import (
    MemoryDatabaseInfo,
    apply_pending_migrations,
    ensure_current_schema,
    read_applied_migrations,
    verify_applied_migrations,
)
from .sqlite_schema import foreign_keys_enabled, validate_schema_compatibility
from .versions import MEMORY_SCHEMA_VERSION

logger = logging.getLogger(__name__)

IN_MEMORY_PATH = ":memory:"
DEFAULT_BUSY_TIMEOUT_MS = DEFAULT_MEMORY_CONFIG.busy_timeout_ms
DEFAULT_SYNCHRONOUS = "NORMAL"


def is_in_memory_path(path: str | Path) -> bool:
    return str(path).strip() == IN_MEMORY_PATH


def validate_memory_db_path(
    path: str | Path,
    *,
    root: Path | None = None,
    must_exist: bool = False,
) -> Path | str:
    """Validate and normalize a memory DB path.

    Returns ``:memory:`` for in-memory tests, otherwise a resolved ``Path``.
    Relative paths require an explicit ``root`` (no silent cwd fallback).
    """
    raw = str(path).strip() if path is not None else ""
    if not raw:
        raise MemoryPersistenceError("Memory database path must not be empty")
    if is_in_memory_path(raw):
        return IN_MEMORY_PATH
    lowered = raw.lower()
    if lowered.startswith("file:") or "mode=" in lowered or "cache=" in lowered:
        raise MemoryPersistenceError("Unsupported SQLite URI-style memory database path")
    if any(sep in raw for sep in ("\x00",)):
        raise MemoryPersistenceError("Memory database path contains invalid characters")

    candidate = Path(raw)
    if not candidate.is_absolute():
        if root is None:
            raise MemoryPersistenceError(
                "Relative memory database path requires an explicit root"
            )
        candidate = (Path(root).resolve() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if root is not None:
        root_resolved = Path(root).resolve()
        if not is_path_under(str(candidate), str(root_resolved)):
            raise MemoryPersistenceError(
                "Memory database path escapes configured root containment"
            )

    if candidate.exists() and candidate.is_dir():
        raise MemoryPersistenceError("Memory database path must not be a directory")
    if must_exist and not candidate.exists():
        raise MemoryPersistenceError("Memory database file does not exist")
    if candidate.suffix.lower() not in {".sqlite3", ".sqlite", ".db"} and candidate.name != IN_MEMORY_PATH:
        # Allow tmp names without extension only when under an explicit root (tests).
        if root is None:
            raise MemoryPersistenceError(
                "Memory database path must use a .sqlite3, .sqlite, or .db suffix"
            )
    return candidate


def _ensure_parent_dir(path: Path, *, create_parents: bool) -> None:
    parent = path.parent
    if parent.exists():
        if not parent.is_dir():
            raise MemoryPersistenceError("Memory database parent path is not a directory")
        return
    if not create_parents:
        raise MemoryPersistenceError(
            "Memory database parent directory does not exist "
            "(pass create_parents=True to create it explicitly)"
        )
    parent.mkdir(parents=True, exist_ok=True)


def configure_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_ms: int,
    file_backed: bool,
) -> None:
    """Apply Phase B2 connection policy (FK, busy_timeout, WAL when file-backed)."""
    if busy_timeout_ms < 0:
        raise MemoryPersistenceError("busy_timeout_ms must be non-negative")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    if file_backed:
        mode_row = conn.execute("PRAGMA journal_mode = WAL").fetchone()
        mode = str(mode_row[0]).lower() if mode_row else ""
        if mode != "wal":
            raise MemoryPersistenceError(
                f"Failed to enable WAL journal_mode (got {mode!r})"
            )
        conn.execute(f"PRAGMA synchronous = {DEFAULT_SYNCHRONOUS}")
    if not foreign_keys_enabled(conn):
        raise MemoryPersistenceError("Failed to enable SQLite foreign_keys")


def open_memory_connection(
    path: str | Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    root: Path | None = None,
    create_parents: bool = False,
) -> sqlite3.Connection:
    """Open a configured SQLite connection (does not run migrations)."""
    validated = validate_memory_db_path(path, root=root)
    try:
        if is_in_memory_path(validated):
            conn = sqlite3.connect(IN_MEMORY_PATH)
            configure_connection(
                conn, busy_timeout_ms=busy_timeout_ms, file_backed=False
            )
            return conn

        assert isinstance(validated, Path)
        _ensure_parent_dir(validated, create_parents=create_parents)
        conn = sqlite3.connect(str(validated))
        try:
            configure_connection(
                conn, busy_timeout_ms=busy_timeout_ms, file_backed=True
            )
        except Exception:
            conn.close()
            raise
        return conn
    except MemoryPersistenceError:
        raise
    except sqlite3.Error as exc:
        raise MemoryPersistenceError("Failed to open memory database connection") from exc


@contextmanager
def memory_connection(
    path: str | Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    root: Path | None = None,
    create_parents: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Context manager that always closes the connection."""
    conn = open_memory_connection(
        path,
        busy_timeout_ms=busy_timeout_ms,
        root=root,
        create_parents=create_parents,
    )
    try:
        yield conn
    finally:
        conn.close()


def initialize_memory_database(
    path: str | Path,
    *,
    config: MemoryConfig | None = None,
    root: Path | None = None,
    create_parents: bool = True,
    require_enabled: bool = True,
) -> MemoryDatabaseInfo:
    """Create/migrate a memory database. Does nothing on package import.

    When ``require_enabled`` is true (default), ``config.enabled`` must be true.
    Tests may pass an explicit enabled ``MemoryConfig``.
    """
    cfg = config if config is not None else DEFAULT_MEMORY_CONFIG
    if require_enabled and not cfg.enabled:
        raise MemoryDisabledError(
            "Shared memory is disabled; refusing database initialization"
        )
    if cfg.backend != "sqlite":
        raise MemoryPersistenceError(f"Unsupported memory backend: {cfg.backend}")

    db_path = path if path is not None else cfg.db_path
    busy = cfg.busy_timeout_ms
    validated = validate_memory_db_path(db_path, root=root)
    in_memory = is_in_memory_path(validated)

    conn = open_memory_connection(
        validated,
        busy_timeout_ms=busy,
        root=None if in_memory else root,
        create_parents=False if in_memory else create_parents,
    )
    try:
        applied = apply_pending_migrations(conn)
        info = MemoryDatabaseInfo(
            path=IN_MEMORY_PATH if in_memory else str(validated),
            schema_compatibility_version=MEMORY_SCHEMA_VERSION,
            applied_migrations=applied,
            in_memory=in_memory,
        )
        logger.info(
            "Memory database initialized schema=%s migrations=%s",
            info.schema_compatibility_version,
            ",".join(info.applied_migrations),
        )
        return info
    except (MemoryMigrationError, MemoryPersistenceError):
        raise
    except sqlite3.Error as exc:
        raise MemoryMigrationError("Memory database initialization failed") from exc
    finally:
        conn.close()


def validate_memory_database(
    path: str | Path,
    *,
    config: MemoryConfig | None = None,
    root: Path | None = None,
    require_enabled: bool = True,
) -> MemoryDatabaseInfo:
    """Open an existing DB and fail closed if migrations/schema are incompatible."""
    cfg = config if config is not None else DEFAULT_MEMORY_CONFIG
    if require_enabled and not cfg.enabled:
        raise MemoryDisabledError(
            "Shared memory is disabled; refusing database validation"
        )
    validated = validate_memory_db_path(path, root=root, must_exist=not is_in_memory_path(path))
    in_memory = is_in_memory_path(validated)
    if in_memory:
        raise MemoryPersistenceError(
            "validate_memory_database requires a file-backed database"
        )

    conn = open_memory_connection(
        validated,
        busy_timeout_ms=cfg.busy_timeout_ms,
        root=root,
        create_parents=False,
    )
    try:
        applied = verify_applied_migrations(conn)
        if not applied:
            raise MemoryMigrationError("Memory database has no applied migrations")
        validate_schema_compatibility(conn)
        return MemoryDatabaseInfo(
            path=str(validated),
            schema_compatibility_version=MEMORY_SCHEMA_VERSION,
            applied_migrations=applied,
            in_memory=False,
        )
    except (MemoryMigrationError, MemoryPersistenceError):
        raise
    except sqlite3.Error as exc:
        raise MemoryMigrationError("Memory database validation failed") from exc
    finally:
        conn.close()


# Re-export helpers used by tests / later layers without widening the CRUD surface.
__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS",
    "IN_MEMORY_PATH",
    "configure_connection",
    "initialize_memory_database",
    "is_in_memory_path",
    "memory_connection",
    "open_memory_connection",
    "validate_memory_database",
    "validate_memory_db_path",
    "ensure_current_schema",
    "read_applied_migrations",
]
