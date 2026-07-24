"""Disabled-by-default memory configuration (no auto DB creation)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryConfig:
    """Pure config record. Does not open or create SQLite files on import."""

    enabled: bool = False
    backend: str = "sqlite"
    db_path: str = "workspace/memory/memory.sqlite3"
    default_retrieve_limit: int = 20
    max_retrieve_limit: int = 100
    busy_timeout_ms: int = 5000
    audit_retrievals: bool = True

    def require_enabled(self) -> None:
        from .errors import MemoryDisabledError

        if not self.enabled:
            raise MemoryDisabledError(
                "Shared memory is disabled (memory.enabled=false). "
                "Refusing enable/write until explicitly configured."
            )


DEFAULT_MEMORY_CONFIG = MemoryConfig()
