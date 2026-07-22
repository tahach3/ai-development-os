"""Persist provider readiness records under workspace/provider_readiness/."""

from __future__ import annotations

import json
from pathlib import Path

from .provider_readiness_models import ProviderReadinessRecord, ReadinessAuditBundle
from .safe_policy import PolicyError, assert_not_equitify_blob


def default_readiness_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "workspace" / "provider_readiness"


class ProviderReadinessStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_readiness_root()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".gitkeep").touch(exist_ok=True)

    def _path(self, readiness_id: str) -> Path:
        assert_not_equitify_blob(readiness_id)
        if "/" in readiness_id or "\\" in readiness_id or ".." in readiness_id:
            raise PolicyError("Invalid readiness_id")
        return self.root / f"{readiness_id}.json"

    def save_record(self, record: ProviderReadinessRecord) -> Path:
        if not record.record_fingerprint:
            record.record_fingerprint = record.compute_fingerprint()
        path = self._path(record.readiness_id)
        path.write_text(
            json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def save_bundle(self, bundle: ReadinessAuditBundle) -> Path:
        if not bundle.record_fingerprint:
            bundle.record_fingerprint = bundle.compute_fingerprint()
        assert_not_equitify_blob(bundle.audit_id)
        path = self.root / f"{bundle.audit_id}.bundle.json"
        path.write_text(
            json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # Also save each provider record.
        for rec in bundle.provider_records:
            self.save_record(rec)
        return path

    def load_record(self, readiness_id: str) -> ProviderReadinessRecord:
        path = self._path(readiness_id)
        if not path.is_file():
            raise PolicyError(f"Readiness record not found: {readiness_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise PolicyError("Corrupted readiness record")
        return ProviderReadinessRecord.from_dict(data)

    def load_bundle(self, audit_id: str) -> dict:
        path = self.root / f"{audit_id}.bundle.json"
        if not path.is_file():
            raise PolicyError(f"Readiness audit bundle not found: {audit_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise PolicyError("Corrupted readiness audit bundle")
        return data
