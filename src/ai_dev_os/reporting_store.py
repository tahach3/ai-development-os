"""Atomic persistence for Round 4C canonical and rendered reports."""

from __future__ import annotations

import json
from pathlib import Path

from .atomic_io import atomic_write_json, atomic_write_text
from .reporting_models import CanonicalReportSnapshot


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class CanonicalReportStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.canonical_dir = base / "reports" / "canonical"
        self.rendered_dir = base / "reports" / "rendered"
        self.manifests_dir = base / "reports" / "manifests"
        self.canonical_dir.mkdir(parents=True, exist_ok=True)
        self.rendered_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def canonical_path(self, report_id: str) -> Path:
        return self.canonical_dir / f"{report_id}.json"

    def rendered_path(self, report_id: str, audience: str, detail: str) -> Path:
        return self.rendered_dir / f"{report_id}.{audience}.{detail}.md"

    def save_canonical(self, snapshot: CanonicalReportSnapshot) -> Path:
        path = self.canonical_path(snapshot.report_id)
        if path.exists():
            # Immutability: refuse silent overwrite of finalized report
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("report_fingerprint") != snapshot.report_fingerprint:
                raise FileExistsError(
                    f"Canonical report {snapshot.report_id} already exists with different fingerprint"
                )
            return path
        atomic_write_json(path, snapshot.to_dict())
        # Manifest of evidence IDs
        manifest_path = self.manifests_dir / f"{snapshot.report_id}.evidence.json"
        atomic_write_json(
            manifest_path,
            {
                "report_id": snapshot.report_id,
                "evidence_ids": [e.evidence_id for e in snapshot.evidence_manifest],
                "source_set_fingerprint": snapshot.source_set_fingerprint,
            },
        )
        return path

    def load_canonical(self, report_id: str) -> CanonicalReportSnapshot:
        path = self.canonical_path(report_id)
        if not path.exists():
            raise FileNotFoundError(f"Canonical report not found: {report_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"corrupted_report:{report_id}") from exc
        return CanonicalReportSnapshot.from_dict(data)

    def save_rendered(
        self,
        snapshot: CanonicalReportSnapshot,
        markdown: str,
    ) -> Path:
        path = self.rendered_path(
            snapshot.report_id, snapshot.audience.value, snapshot.detail_level.value
        )
        atomic_write_text(path, markdown)
        snapshot.rendered_paths[
            f"{snapshot.audience.value}:{snapshot.detail_level.value}"
        ] = str(path)
        return path
