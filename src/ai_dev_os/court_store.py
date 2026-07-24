"""Persist Constitutional Court records under workspace/court_records/."""

from __future__ import annotations

import json
from pathlib import Path

from .atomic_io import atomic_write_json
from .constitutional_court import CourtRecord
from .validation import ValidationError


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class CourtStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.root = base / "court_records"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: CourtRecord) -> Path:
        path = self.root / f"{record.record_id}.json"
        atomic_write_json(path, record.to_dict())
        return path

    def load(self, record_id: str) -> CourtRecord:
        path = self.root / f"{record_id}.json"
        if not path.is_file():
            raise ValidationError(f"Court record not found: {record_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return CourtRecord.from_dict(data)

    def list_for_plan(self, plan_id: str) -> list[CourtRecord]:
        records: list[CourtRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(data.get("plan_id") or "") != plan_id:
                continue
            records.append(CourtRecord.from_dict(data))
        return records

    def latest_passing_for_plan(self, plan_id: str, plan_fingerprint: str) -> CourtRecord | None:
        """Most recent required pass/pass_with_notes matching plan fingerprint."""
        from .constitutional_court import CourtVerdict

        matches: list[CourtRecord] = []
        for rec in self.list_for_plan(plan_id):
            if not rec.required:
                continue
            if rec.verdict not in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES):
                continue
            if rec.plan_fingerprint != plan_fingerprint:
                continue
            matches.append(rec)
        if not matches:
            return None
        return sorted(matches, key=lambda r: r.evaluated_at)[-1]

    def list_all(self) -> list[CourtRecord]:
        """Load all persisted Court records (deterministic path order)."""
        records: list[CourtRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            try:
                records.append(CourtRecord.from_dict(data))
            except (KeyError, TypeError, ValueError):
                continue
        return records

    def format_ci_visibility_notes(self, *, limit: int = 5) -> list[str]:
        """Informational CI notes when Court records exist — never a failure class.

        Surfaces record_id, plan_id, plan_fingerprint, and verdict only.
        """
        notes: list[str] = []
        for rec in self.list_all()[: max(0, limit)]:
            verdict = rec.verdict.value if hasattr(rec.verdict, "value") else str(rec.verdict)
            notes.append(
                "court_record_present: "
                f"record_id={rec.record_id} "
                f"plan_id={rec.plan_id} "
                f"plan_fingerprint={rec.plan_fingerprint} "
                f"verdict={verdict}"
            )
        return notes
