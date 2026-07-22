"""Host-local executable pinning for provider readiness (Round 4D1.1)."""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .fingerprints import fingerprint
from .models import utc_now_iso
from .provider_readiness_constants import (
    EXECUTABLE_PIN_SCHEMA_VERSION,
    EXECUTABLE_TRUST_POLICY_VERSION,
)
from .provider_readiness_discovery import hash_executable, sanitize_executable_location
from .safe_policy import PolicyError, assert_not_equitify_blob


def default_pins_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "workspace" / "provider_pins"


def host_binding_fingerprint() -> str:
    return fingerprint(
        {
            "platform": platform.system().lower(),
            "machine": platform.machine().lower(),
            "node_class": "local_host",
        }
    )


@dataclass
class ExecutablePin:
    pin_id: str
    schema_version: str
    provider_id: str
    candidate_id: str
    canonical_executable_path: str
    expected_fingerprint: str
    expected_cli_version: str | None
    adapter_id: str
    adapter_version: str
    trust_policy_version: str
    host_binding_fingerprint: str
    pin_status: str
    created_at: str
    approval_phrase: str
    decision_id: str | None = None
    expires_at: str | None = None
    pin_fingerprint: str = ""
    notes: str = ""

    def compute_fingerprint(self) -> str:
        payload = asdict(self)
        payload.pop("pin_fingerprint", None)
        payload.pop("created_at", None)
        return fingerprint(payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        """Never expose full private path in public views."""
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "candidate_id": self.candidate_id,
            "created_at": self.created_at,
            "decision_id": self.decision_id,
            "expected_cli_version": self.expected_cli_version,
            "expected_fingerprint": self.expected_fingerprint,
            "expires_at": self.expires_at,
            "host_binding_fingerprint": self.host_binding_fingerprint,
            "notes": self.notes,
            "path_label": sanitize_executable_location(self.canonical_executable_path),
            "pin_fingerprint": self.pin_fingerprint,
            "pin_id": self.pin_id,
            "pin_status": self.pin_status,
            "provider_id": self.provider_id,
            "schema_version": self.schema_version,
            "trust_policy_version": self.trust_policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutablePin:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)


class PinValidationResult:
    def __init__(
        self,
        *,
        valid: bool,
        status: str,
        reasons: list[str],
        pin: ExecutablePin | None = None,
        live_mode_enabled: bool = False,
        authentication_implied: bool = False,
    ) -> None:
        self.valid = valid
        self.status = status
        self.reasons = reasons
        self.pin = pin
        self.live_mode_enabled = live_mode_enabled
        self.authentication_implied = authentication_implied

    def to_dict(self) -> dict[str, Any]:
        return {
            "authentication_implied": self.authentication_implied,
            "live_mode_enabled": self.live_mode_enabled,
            "pin": self.pin.to_public_dict() if self.pin else None,
            "reasons": list(self.reasons),
            "status": self.status,
            "valid": self.valid,
        }


class ProviderPinStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_pins_root()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".gitkeep").touch(exist_ok=True)

    def _path(self, provider_id: str) -> Path:
        assert_not_equitify_blob(provider_id)
        if "/" in provider_id or "\\" in provider_id or ".." in provider_id:
            raise PolicyError("Invalid provider_id for pin")
        return self.root / f"{provider_id}.pin.json"

    def load(self, provider_id: str) -> ExecutablePin | None:
        path = self._path(provider_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise PolicyError("Corrupted pin record")
        return ExecutablePin.from_dict(data)

    def save(self, pin: ExecutablePin) -> Path:
        if not pin.expected_fingerprint:
            raise PolicyError("Path-only pins are rejected; fingerprint required")
        if not pin.canonical_executable_path:
            raise PolicyError("Pin requires canonical executable path")
        assert_not_equitify_blob(pin.canonical_executable_path, pin.provider_id)
        pin.pin_fingerprint = pin.compute_fingerprint()
        path = self._path(pin.provider_id)
        path.write_text(
            json.dumps(pin.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path


def create_pin(
    *,
    provider_id: str,
    candidate_id: str,
    canonical_executable_path: str,
    expected_fingerprint: str,
    adapter_id: str,
    adapter_version: str,
    approval_phrase: str,
    expected_cli_version: str | None = None,
    decision_id: str | None = None,
    trust_policy_version: str = EXECUTABLE_TRUST_POLICY_VERSION,
) -> ExecutablePin:
    if not expected_fingerprint or not str(expected_fingerprint).strip():
        raise PolicyError("Path-only pins are rejected; fingerprint required")
    assert_not_equitify_blob(canonical_executable_path, provider_id)
    pin = ExecutablePin(
        pin_id=f"pin_{uuid4().hex[:16]}",
        schema_version=EXECUTABLE_PIN_SCHEMA_VERSION,
        provider_id=provider_id,
        candidate_id=candidate_id,
        canonical_executable_path=str(Path(canonical_executable_path).resolve()),
        expected_fingerprint=expected_fingerprint,
        expected_cli_version=expected_cli_version,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        trust_policy_version=trust_policy_version,
        host_binding_fingerprint=host_binding_fingerprint(),
        pin_status="active",
        created_at=utc_now_iso(),
        approval_phrase=approval_phrase,
        decision_id=decision_id,
    )
    pin.pin_fingerprint = pin.compute_fingerprint()
    return pin


def validate_pin(
    pin: ExecutablePin,
    *,
    adapter_version: str,
    trust_policy_version: str = EXECUTABLE_TRUST_POLICY_VERSION,
    current_cli_version: str | None = None,
    require_host_match: bool = True,
) -> PinValidationResult:
    reasons: list[str] = []
    if not pin.expected_fingerprint:
        return PinValidationResult(
            valid=False, status="executable_pin_invalid", reasons=["path_only_pin_rejected"], pin=pin
        )
    if pin.schema_version != EXECUTABLE_PIN_SCHEMA_VERSION:
        reasons.append("pin_schema_mismatch")
    if require_host_match and pin.host_binding_fingerprint != host_binding_fingerprint():
        reasons.append("host_mismatch")
    if pin.adapter_version != adapter_version:
        reasons.append("adapter_version_mismatch")
    if pin.trust_policy_version != trust_policy_version:
        reasons.append("trust_policy_mismatch")

    path = Path(pin.canonical_executable_path)
    try:
        assert_not_equitify_blob(str(path))
    except PolicyError:
        reasons.append("equitify_rejected")
        return PinValidationResult(
            valid=False, status="executable_pin_invalid", reasons=reasons, pin=pin
        )

    if not path.exists():
        reasons.append("executable_missing")
        return PinValidationResult(
            valid=False, status="executable_pin_stale", reasons=reasons, pin=pin
        )

    actual_fp = hash_executable(path)
    if actual_fp != pin.expected_fingerprint:
        reasons.append("fingerprint_mismatch")
        return PinValidationResult(
            valid=False, status="executable_pin_invalid", reasons=reasons, pin=pin
        )

    if pin.expected_cli_version and current_cli_version is not None:
        if current_cli_version != pin.expected_cli_version:
            reasons.append("cli_version_mismatch")
            return PinValidationResult(
                valid=False, status="executable_pin_stale", reasons=reasons, pin=pin
            )

    if reasons:
        return PinValidationResult(
            valid=False, status="executable_pin_invalid", reasons=reasons, pin=pin
        )

    return PinValidationResult(
        valid=True,
        status="active",
        reasons=[],
        pin=pin,
        live_mode_enabled=False,
        authentication_implied=False,
    )
