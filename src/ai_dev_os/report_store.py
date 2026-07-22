"""Store implementation and review reports."""

from __future__ import annotations

import json
from pathlib import Path

from .fingerprints import (
    fingerprint_implementation_report,
    fingerprint_review_report,
)
from .models import ImplementationReport, ReviewReport, utc_now_iso


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class ReportStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.impl_dir = base / "reports" / "implementation"
        self.review_dir = base / "reports" / "review"
        self.impl_dir.mkdir(parents=True, exist_ok=True)
        self.review_dir.mkdir(parents=True, exist_ok=True)

    def save_implementation(self, report: ImplementationReport) -> Path:
        data = report.to_dict()
        report.content_fingerprint = fingerprint_implementation_report(data)
        data = report.to_dict()
        path = self.impl_dir / f"{report.task_id}.{_stamp()}.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    def save_review(self, report: ReviewReport) -> Path:
        data = report.to_dict()
        report.content_fingerprint = fingerprint_review_report(data)
        data = report.to_dict()
        path = self.review_dir / f"{report.task_id}.{_stamp()}.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    def list_implementation(self, task_id: str | None = None) -> list[ImplementationReport]:
        reports: list[ImplementationReport] = []
        for path in sorted(self.impl_dir.glob("*.json")):
            if task_id and not path.name.startswith(f"{task_id}."):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            reports.append(ImplementationReport.from_dict(data))
        return reports

    def list_reviews(self, task_id: str | None = None) -> list[ReviewReport]:
        reports: list[ReviewReport] = []
        for path in sorted(self.review_dir.glob("*.json")):
            if task_id and not path.name.startswith(f"{task_id}."):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            reports.append(ReviewReport.from_dict(data))
        return reports

    def latest_review(self, task_id: str) -> ReviewReport | None:
        reviews = self.list_reviews(task_id)
        return reviews[-1] if reviews else None

    def latest_implementation(self, task_id: str) -> ImplementationReport | None:
        reports = self.list_implementation(task_id)
        return reports[-1] if reports else None


def _stamp() -> str:
    return utc_now_iso().replace(":", "").replace("+00:00", "Z")
