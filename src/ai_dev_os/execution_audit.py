"""Persistent execution audit records with deterministic JSON serialization."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .execution_models import ExecutionEnvelope


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def serialize_envelope(envelope: ExecutionEnvelope) -> str:
    """Deterministic JSON: sorted keys, stable indent."""
    return json.dumps(envelope.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


class ExecutionAuditStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.executions_dir = base / "executions"
        self.executions_dir.mkdir(parents=True, exist_ok=True)

    def save(self, envelope: ExecutionEnvelope) -> Path:
        if not envelope.execution_id:
            envelope.execution_id = f"exec-{uuid.uuid4().hex[:12]}"
        path = self.executions_dir / f"{envelope.execution_id}.json"
        path.write_text(serialize_envelope(envelope), encoding="utf-8")
        return path

    def load(self, execution_id: str) -> ExecutionEnvelope:
        path = self.executions_dir / f"{execution_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Execution not found: {execution_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExecutionEnvelope.from_dict(data)

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.executions_dir.glob("*.json"))
