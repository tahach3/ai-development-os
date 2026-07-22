"""Persistent provider execution audit records."""

from __future__ import annotations

import json
from pathlib import Path

from .provider_models import ProviderRequest, ProviderResultEnvelope, validate_provider_result_dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def serialize_provider_result(envelope: ProviderResultEnvelope) -> str:
    return json.dumps(envelope.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


class ProviderAuditStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.root = base / "provider_executions"
        self.root.mkdir(parents=True, exist_ok=True)
        self.requests_dir = self.root / "requests"
        self.results_dir = self.root / "results"
        self.artifacts_dir = self.root / "artifacts"
        self.cancel_dir = self.root / "cancel"
        for d in (self.requests_dir, self.results_dir, self.artifacts_dir, self.cancel_dir):
            d.mkdir(parents=True, exist_ok=True)

    def save_request(self, request: ProviderRequest) -> Path:
        path = self.requests_dir / f"{request.request_id}.json"
        path.write_text(
            json.dumps(request.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def load_request(self, request_id: str) -> ProviderRequest:
        path = self.requests_dir / f"{request_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Provider request not found: {request_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProviderRequest.from_dict(data)

    def save_result(self, envelope: ProviderResultEnvelope) -> Path:
        path = self.results_dir / f"{envelope.request_id}.json"
        path.write_text(serialize_provider_result(envelope), encoding="utf-8")
        return path

    def load_result(self, request_id: str) -> ProviderResultEnvelope:
        path = self.results_dir / f"{request_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Provider result not found: {request_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_provider_result_dict(data)
        # Load always works for show; intake uses separate validation.
        _ = errors
        return ProviderResultEnvelope.from_dict(data)

    def find_by_fingerprint(self, request_fingerprint: str) -> ProviderResultEnvelope | None:
        for path in sorted(self.results_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("request_fingerprint") == request_fingerprint:
                return ProviderResultEnvelope.from_dict(data)
        return None

    def list_request_ids(self) -> list[str]:
        return sorted(p.stem for p in self.requests_dir.glob("*.json"))

    def request_cancel(self, request_id: str) -> Path:
        path = self.cancel_dir / f"{request_id}.flag"
        path.write_text("cancel\n", encoding="utf-8")
        return path

    def is_cancel_requested(self, request_id: str) -> bool:
        return (self.cancel_dir / f"{request_id}.flag").exists()

    def artifact_path(self, request_id: str, name: str = "result.json") -> Path:
        d = self.artifacts_dir / request_id
        d.mkdir(parents=True, exist_ok=True)
        return d / name
