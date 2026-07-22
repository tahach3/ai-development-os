"""Durable orchestration store with atomic replace semantics."""

from __future__ import annotations

from pathlib import Path

import yaml

from .atomic_io import atomic_write_yaml
from .models import utc_now_iso
from .orchestration_models import (
    CompletionSummary,
    OrchestrationEvent,
    OrchestrationRecord,
    RoundEvidence,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class OrchestrationStoreError(ValueError):
    pass


class OrchestrationStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.workspace_root = base
        self.root = base / "orchestrations"
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, orchestration_id: str) -> Path:
        return self.root / orchestration_id

    def record_path(self, orchestration_id: str) -> Path:
        return self._dir(orchestration_id) / "orchestration.yaml"

    def events_path(self, orchestration_id: str) -> Path:
        return self._dir(orchestration_id) / "events.yaml"

    def rounds_dir(self, orchestration_id: str) -> Path:
        return self._dir(orchestration_id) / "rounds"

    def summary_path(self, orchestration_id: str) -> Path:
        return self._dir(orchestration_id) / "completion_summary.yaml"

    def exists(self, orchestration_id: str) -> bool:
        return self.record_path(orchestration_id).exists()

    def save_record(self, record: OrchestrationRecord) -> Path:
        path = self.record_path(record.orchestration_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record.updated_at = utc_now_iso()
        atomic_write_yaml(path, record.to_dict())
        return path

    def load_record(self, orchestration_id: str) -> OrchestrationRecord:
        path = self.record_path(orchestration_id)
        if not path.exists():
            raise OrchestrationStoreError(f"Orchestration not found: {orchestration_id}")
        # Reject partial temp leftovers as authoritative.
        tmp = path.with_name(path.name + ".tmp")
        if tmp.exists() and not path.exists():
            raise OrchestrationStoreError(
                f"Partial orchestration write detected for {orchestration_id}"
            )
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        try:
            return OrchestrationRecord.from_dict(data)
        except ValueError as exc:
            raise OrchestrationStoreError(str(exc)) from exc

    def list_ids(self) -> list[str]:
        return sorted(
            p.name for p in self.root.iterdir() if p.is_dir() and (p / "orchestration.yaml").exists()
        )

    def load_events(self, orchestration_id: str) -> list[OrchestrationEvent]:
        path = self.events_path(orchestration_id)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        items = data.get("events") or []
        return [OrchestrationEvent.from_dict(item) for item in items]

    def append_event(self, event: OrchestrationEvent) -> Path:
        path = self.events_path(event.orchestration_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        events = self.load_events(event.orchestration_id)
        if any(e.event_id == event.event_id for e in events):
            # Idempotent: already recorded.
            return path
        if not event.created_at:
            event.created_at = utc_now_iso()
        events.append(event)
        payload = {
            "orchestration_id": event.orchestration_id,
            "events": [e.to_dict() for e in events],
        }
        atomic_write_yaml(path, payload)
        return path

    def save_round(self, evidence: RoundEvidence) -> Path:
        d = self.rounds_dir(evidence.orchestration_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"round-{evidence.round_number:04d}.yaml"
        atomic_write_yaml(path, evidence.to_dict())
        return path

    def load_rounds(self, orchestration_id: str) -> list[RoundEvidence]:
        d = self.rounds_dir(orchestration_id)
        if not d.exists():
            return []
        rounds: list[RoundEvidence] = []
        for path in sorted(d.glob("round-*.yaml")):
            with path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            rounds.append(RoundEvidence.from_dict(data))
        return rounds

    def save_summary(self, summary: CompletionSummary) -> Path:
        path = self.summary_path(summary.orchestration_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_yaml(path, summary.to_dict())
        return path

    def load_summary(self, orchestration_id: str) -> CompletionSummary | None:
        path = self.summary_path(orchestration_id)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return CompletionSummary.from_dict(data)

    def find_active_for_task(self, task_id: str) -> OrchestrationRecord | None:
        for oid in self.list_ids():
            rec = self.load_record(oid)
            if rec.task_id == task_id and not rec.is_terminal():
                return rec
        return None
