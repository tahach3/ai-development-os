"""Forward-only SQLite migration runner for shared memory (Phase B3.2)."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from typing import Sequence

from ai_dev_os.models import utc_now_iso

from .errors import MemoryMigrationError
from .sqlite_schema import build_initial_schema_sql, validate_schema_compatibility
from .versions import MEMORY_SCHEMA_VERSION

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryMigration:
    """Immutable registered migration (forward-only)."""

    version: str
    name: str
    description: str
    sql: str

    @property
    def checksum(self) -> str:
        return checksum_migration_sql(self.sql)


def checksum_migration_sql(sql: str) -> str:
    """Deterministic SHA-256 of normalized migration SQL."""
    normalized = sql.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _migration_001() -> MemoryMigration:
    return MemoryMigration(
        version="001",
        name="initial_memory_schema",
        description=(
            "Create schema_migrations and Phase B2 memory tables "
            f"(compatibility {MEMORY_SCHEMA_VERSION}); FTS5 deferred."
        ),
        sql=build_initial_schema_sql(),
    )


REGISTERED_MIGRATIONS: tuple[MemoryMigration, ...] = (_migration_001(),)

SUPPORTED_MIGRATION_VERSIONS: frozenset[str] = frozenset(
    m.version for m in REGISTERED_MIGRATIONS
)


@dataclass(frozen=True)
class AppliedMigrationRow:
    version: str
    name: str
    checksum: str
    applied_at: str
    description: str


@dataclass(frozen=True)
class MemoryDatabaseInfo:
    """Bootstrap / validation result (no CRUD)."""

    path: str
    schema_compatibility_version: str
    applied_migrations: tuple[str, ...]
    in_memory: bool = False


def migrations_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    return row is not None


def read_applied_migrations(conn: sqlite3.Connection) -> dict[str, AppliedMigrationRow]:
    if not migrations_table_exists(conn):
        return {}
    rows = conn.execute(
        "SELECT version, name, checksum, applied_at, description "
        "FROM schema_migrations ORDER BY version ASC"
    ).fetchall()
    out: dict[str, AppliedMigrationRow] = {}
    for version, name, checksum, applied_at, description in rows:
        out[str(version)] = AppliedMigrationRow(
            version=str(version),
            name=str(name),
            checksum=str(checksum),
            applied_at=str(applied_at),
            description=str(description),
        )
    return out


def verify_applied_migrations(
    conn: sqlite3.Connection,
    *,
    registered: Sequence[MemoryMigration] = REGISTERED_MIGRATIONS,
) -> tuple[str, ...]:
    """Verify applied history against registry; fail closed on mismatch/unknown."""
    applied = read_applied_migrations(conn)
    registry = {m.version: m for m in registered}

    for version, row in applied.items():
        if version not in registry:
            raise MemoryMigrationError(
                f"Unknown future or unregistered migration version present: {version}"
            )
        expected = registry[version]
        if row.name != expected.name:
            raise MemoryMigrationError(
                f"Migration name mismatch for version {version}"
            )
        if row.checksum != expected.checksum:
            raise MemoryMigrationError(
                f"Migration checksum mismatch for version {version}"
            )

    # Applied set must be a contiguous prefix of registered order.
    applied_versions = list(applied.keys())
    expected_prefix = [m.version for m in registered[: len(applied_versions)]]
    if applied_versions != expected_prefix:
        raise MemoryMigrationError(
            "Applied migrations are incomplete or out of order relative to registry"
        )

    # Ambiguous schema: tables exist but no migration history.
    if not applied:
        tables = {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        unexpected = tables - {"schema_migrations"}
        if unexpected:
            raise MemoryMigrationError(
                "Ambiguous schema: memory tables exist without migration history"
            )

    return tuple(applied_versions)


def apply_pending_migrations(
    conn: sqlite3.Connection,
    *,
    registered: Sequence[MemoryMigration] = REGISTERED_MIGRATIONS,
) -> tuple[str, ...]:
    """Apply pending migrations atomically; idempotent when already current."""
    applied = verify_applied_migrations(conn, registered=registered)
    pending = [m for m in registered if m.version not in applied]

    for migration in pending:
        logger.info(
            "Applying memory migration version=%s name=%s",
            migration.version,
            migration.name,
        )
        # Explicit transactions: avoid executescript (auto-COMMIT) and implicit
        # isolation ambiguity so DDL + migration row commit or roll back together.
        previous_isolation = conn.isolation_level
        try:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            for statement in split_sql_statements(migration.sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations "
                "(version, name, checksum, applied_at, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    utc_now_iso(),
                    migration.description,
                ),
            )
            conn.execute("COMMIT")
        except MemoryMigrationError:
            _safe_rollback(conn)
            raise
        except sqlite3.Error as exc:
            _safe_rollback(conn)
            raise MemoryMigrationError(
                f"Migration {migration.version} failed and was rolled back"
            ) from exc
        except Exception as exc:
            _safe_rollback(conn)
            raise MemoryMigrationError(
                f"Migration {migration.version} failed unexpectedly"
            ) from exc
        finally:
            conn.isolation_level = previous_isolation
        logger.info(
            "Memory migration applied version=%s status=success",
            migration.version,
        )

    final = verify_applied_migrations(conn, registered=registered)
    validate_schema_compatibility(conn)
    return final


def _safe_rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass


def split_sql_statements(sql: str) -> list[str]:
    """Split controlled migration SQL into statements (no string-literal DDL)."""
    normalized = sql.replace("\r\n", "\n").replace("\r", "\n")
    statements: list[str] = []
    for part in normalized.split(";"):
        stmt = part.strip()
        if stmt:
            statements.append(stmt)
    return statements


def ensure_current_schema(conn: sqlite3.Connection) -> MemoryDatabaseInfo:
    """Apply pending migrations and validate compatibility (caller owns connection)."""
    applied = apply_pending_migrations(conn)
    return MemoryDatabaseInfo(
        path=":memory:" if _is_memory_path_label(conn) else "(file)",
        schema_compatibility_version=MEMORY_SCHEMA_VERSION,
        applied_migrations=applied,
        in_memory=_is_memory_path_label(conn),
    )


def _is_memory_path_label(conn: sqlite3.Connection) -> bool:
    row = conn.execute("PRAGMA database_list").fetchone()
    # (seq, name, file) — file empty for :memory:
    if row is None:
        return True
    return not str(row[2] or "")
