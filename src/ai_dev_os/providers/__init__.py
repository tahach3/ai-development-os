"""Provider adapter registry."""

from __future__ import annotations

from .base import ProviderAdapter
from .cli_shells import ClaudeCodeCliAdapter, CodexCliAdapter, CursorCliAdapter
from .simulated import SimulatedProviderAdapter


_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "simulated": SimulatedProviderAdapter,
    "claude_code": ClaudeCodeCliAdapter,
    "codex": CodexCliAdapter,
    "cursor": CursorCliAdapter,
}


def list_provider_ids() -> list[str]:
    return sorted(_ADAPTERS.keys())


def get_provider_adapter(provider_id: str) -> ProviderAdapter:
    try:
        cls = _ADAPTERS[provider_id]
    except KeyError as exc:
        raise KeyError(f"Unknown provider adapter: {provider_id}") from exc
    return cls()


__all__ = [
    "ProviderAdapter",
    "SimulatedProviderAdapter",
    "ClaudeCodeCliAdapter",
    "CodexCliAdapter",
    "CursorCliAdapter",
    "list_provider_ids",
    "get_provider_adapter",
]
