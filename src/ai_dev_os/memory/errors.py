"""Typed domain errors for shared memory (fail closed; no secrets in messages)."""

from __future__ import annotations

from ai_dev_os.validation import ValidationError


class MemoryError(Exception):
    """Base error for the memory domain."""


class MemoryDisabledError(MemoryError):
    """Raised when memory is disabled (default)."""


class MemoryNotFoundError(MemoryError):
    """Raised when a memory id is unknown or not visible in project scope."""


class MemoryValidationError(ValidationError, MemoryError):
    """Schema, enum, content, id, or hash validation failure."""


class MemorySecurityError(MemoryError):
    """Secrets, prohibited sensitivity, or Equitify/security policy refusal."""


class MemoryAuthorizationError(MemoryError):
    """Actor is not permitted to perform the requested memory action."""


class MemoryConflictError(MemoryError):
    """Illegal lifecycle transition, stale hash, or supersession conflict."""


class MemoryIsolationError(MemoryError):
    """Project-scope isolation violation."""


class MemoryPersistenceError(MemoryError):
    """SQLite path, connection, or backend configuration failure."""


class MemoryMigrationError(MemoryError):
    """Schema migration apply/verify failure (fail closed)."""
