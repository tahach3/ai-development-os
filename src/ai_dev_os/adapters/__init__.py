"""Manual-handoff adapters for Claude, Cursor, and Codex."""

from .base import AdapterResult, BaseAdapter, ManualHandoffAdapter
from .claude_adapter import ClaudeAdapter
from .codex_adapter import CodexAdapter
from .cursor_adapter import CursorAdapter

__all__ = [
    "AdapterResult",
    "BaseAdapter",
    "ManualHandoffAdapter",
    "ClaudeAdapter",
    "CursorAdapter",
    "CodexAdapter",
    "get_adapter",
]


def get_adapter(role: str) -> BaseAdapter:
    mapping = {
        "claude": ClaudeAdapter,
        "cursor": CursorAdapter,
        "codex": CodexAdapter,
    }
    try:
        cls = mapping[role]
    except KeyError as exc:
        raise KeyError(f"Unknown adapter role: {role}") from exc
    return cls()
