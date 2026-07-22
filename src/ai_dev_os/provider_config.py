"""Versioned provider configuration — fail-closed defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .provider_models import (
    PROVIDER_CONFIG_SCHEMA_VERSION,
    ProviderId,
    ProviderMode,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_providers_config_path() -> Path:
    return _repo_root() / "config" / "providers.yaml"


def example_providers_config_path() -> Path:
    return _repo_root() / "config" / "providers.example.yaml"


@dataclass
class ProviderEntryConfig:
    provider_id: str
    mode: ProviderMode = ProviderMode.DISABLED
    executable_path: str | None = None
    enabled: bool = False
    allow_live: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_live": self.allow_live,
            "enabled": self.enabled,
            "executable_path": self.executable_path,
            "mode": self.mode.value,
            "notes": self.notes,
            "provider_id": self.provider_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderEntryConfig:
        mode_raw = data.get("mode") or ProviderMode.DISABLED.value
        return cls(
            provider_id=str(data.get("provider_id") or ""),
            mode=ProviderMode(mode_raw),
            executable_path=data.get("executable_path"),
            enabled=bool(data.get("enabled", False)),
            allow_live=bool(data.get("allow_live", False)),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class ProviderConfig:
    schema_version: str = PROVIDER_CONFIG_SCHEMA_VERSION
    default_mode: ProviderMode = ProviderMode.DISABLED
    providers: dict[str, ProviderEntryConfig] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_mode": self.default_mode.value,
            "providers": {
                pid: entry.to_dict()
                for pid, entry in sorted(self.providers.items(), key=lambda x: x[0])
            },
            "schema_version": self.schema_version,
        }

    def sanitized_public_dict(self) -> dict[str, Any]:
        """Config view safe for CLI status — no secrets (none stored)."""
        return self.to_dict()

    def get_entry(self, provider_id: str) -> ProviderEntryConfig:
        if provider_id in self.providers:
            return self.providers[provider_id]
        return ProviderEntryConfig(
            provider_id=provider_id,
            mode=self.default_mode,
            enabled=False,
            allow_live=False,
        )

    def effective_mode(self, provider_id: str) -> ProviderMode:
        entry = self.get_entry(provider_id)
        if not entry.enabled and entry.mode is not ProviderMode.DISABLED:
            # Fail closed: disabled unless explicitly enabled.
            if entry.mode is ProviderMode.LIVE_LOCAL_CLI_ALLOWED:
                return ProviderMode.DISABLED
        if not entry.enabled:
            return ProviderMode.DISABLED
        if entry.mode is ProviderMode.LIVE_LOCAL_CLI_ALLOWED and not entry.allow_live:
            return ProviderMode.DISABLED
        return entry.mode


def fail_closed_default_config() -> ProviderConfig:
    providers = {
        ProviderId.SIMULATED.value: ProviderEntryConfig(
            provider_id=ProviderId.SIMULATED.value,
            mode=ProviderMode.DISABLED,
            enabled=False,
            allow_live=False,
            notes="Synthetic fixture provider; enable mode=simulated for tests.",
        ),
        ProviderId.CLAUDE_CODE.value: ProviderEntryConfig(
            provider_id=ProviderId.CLAUDE_CODE.value,
            mode=ProviderMode.DISABLED,
            enabled=False,
            allow_live=False,
            notes="Claude Code CLI adapter shell; live not authorized by default.",
        ),
        ProviderId.CODEX.value: ProviderEntryConfig(
            provider_id=ProviderId.CODEX.value,
            mode=ProviderMode.DISABLED,
            enabled=False,
            allow_live=False,
            notes="Codex CLI adapter shell; live not authorized by default.",
        ),
        ProviderId.CURSOR.value: ProviderEntryConfig(
            provider_id=ProviderId.CURSOR.value,
            mode=ProviderMode.DISABLED,
            enabled=False,
            allow_live=False,
            notes="Cursor CLI only if safely detectable; else manual_handoff.",
        ),
    }
    return ProviderConfig(
        schema_version=PROVIDER_CONFIG_SCHEMA_VERSION,
        default_mode=ProviderMode.DISABLED,
        providers=providers,
    )


def load_provider_config(path: Path | None = None) -> ProviderConfig:
    cfg_path = path or default_providers_config_path()
    if not cfg_path.exists():
        return fail_closed_default_config()
    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        return fail_closed_default_config()
    default_mode = ProviderMode(raw.get("default_mode") or ProviderMode.DISABLED.value)
    providers: dict[str, ProviderEntryConfig] = {}
    for pid, entry in (raw.get("providers") or {}).items():
        if not isinstance(entry, dict):
            continue
        data = dict(entry)
        data.setdefault("provider_id", pid)
        providers[str(pid)] = ProviderEntryConfig.from_dict(data)
    # Ensure known providers exist with fail-closed fill.
    base = fail_closed_default_config()
    for pid, default_entry in base.providers.items():
        if pid not in providers:
            providers[pid] = default_entry
    return ProviderConfig(
        schema_version=str(raw.get("schema_version") or PROVIDER_CONFIG_SCHEMA_VERSION),
        default_mode=default_mode,
        providers=providers,
    )


def save_provider_config(config: ProviderConfig, path: Path | None = None) -> Path:
    cfg_path = path or default_providers_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config.to_dict(), fh, sort_keys=False)
    return cfg_path
