"""Round 4A hardening — CI run history index and regression comparison.

Turns the pile of persisted ``workspace/ci_runs/*.json`` audit records into a
usable, deterministic history: list past runs, find the latest / latest-passing
run, and compare any two runs to separate a *new* regression from a
pre-existing failure. Reading is intentionally defensive — records written by a
future schema version are surfaced, not crashed on — so the audit trail stays
readable across rounds (historical compatibility).

Read-only and additive: it never mutates or deletes audit records and never
changes CI execution behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ci_models import CI_POLICY_VERSION, CI_SCHEMA_VERSION, CIVerdict

PASSING_VERDICTS = frozenset(
    {CIVerdict.PASS.value, CIVerdict.PASS_WITH_NOTES.value}
)


def _default_runs_dir(repo_root: Path, results_dirname: str = "ci_runs") -> Path:
    return Path(repo_root).resolve() / "workspace" / results_dirname


@dataclass
class CIRunIndexEntry:
    run_id: str
    started_at: str
    finished_at: str
    final_verdict: str
    failure_classes: list[str]
    starting_commit: str
    trigger_type: str
    tests_passed: int | None
    tests_failed: int | None
    tests_skipped: int | None
    schema_version: str
    path: str
    readable: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "final_verdict": self.final_verdict,
            "failure_classes": list(self.failure_classes),
            "starting_commit": self.starting_commit,
            "trigger_type": self.trigger_type,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "schema_version": self.schema_version,
            "path": self.path,
            "readable": self.readable,
            "note": self.note,
        }


def _entry_from_path(repo_root: Path, path: Path) -> CIRunIndexEntry:
    rel = path.relative_to(Path(repo_root).resolve()).as_posix()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CIRunIndexEntry(
            run_id=path.stem,
            started_at="",
            finished_at="",
            final_verdict="unreadable",
            failure_classes=[],
            starting_commit="",
            trigger_type="",
            tests_passed=None,
            tests_failed=None,
            tests_skipped=None,
            schema_version="",
            path=rel,
            readable=False,
            note=f"unreadable: {exc}",
        )
    if not isinstance(raw, dict):
        return CIRunIndexEntry(
            run_id=path.stem, started_at="", finished_at="", final_verdict="unreadable",
            failure_classes=[], starting_commit="", trigger_type="", tests_passed=None,
            tests_failed=None, tests_skipped=None, schema_version="", path=rel,
            readable=False, note="record root is not an object",
        )
    sv = str(raw.get("schema_version", ""))
    note = ""
    if sv and sv != CI_SCHEMA_VERSION:
        note = f"schema_version {sv} differs from current {CI_SCHEMA_VERSION}"
    return CIRunIndexEntry(
        run_id=str(raw.get("run_id", path.stem)),
        started_at=str(raw.get("started_at", "")),
        finished_at=str(raw.get("finished_at", "")),
        final_verdict=str(raw.get("final_verdict", "")),
        failure_classes=[str(f) for f in (raw.get("failure_classes") or [])],
        starting_commit=str(raw.get("starting_commit", "")),
        trigger_type=str(raw.get("trigger_type", "")),
        tests_passed=raw.get("tests_passed"),
        tests_failed=raw.get("tests_failed"),
        tests_skipped=raw.get("tests_skipped"),
        schema_version=sv,
        path=rel,
        readable=True,
        note=note,
    )


def list_runs(
    repo_root: Path,
    *,
    results_dirname: str = "ci_runs",
    limit: int | None = None,
) -> list[CIRunIndexEntry]:
    """Return persisted CI runs, most recent first (deterministic order)."""
    runs_dir = _default_runs_dir(repo_root, results_dirname)
    if not runs_dir.is_dir():
        return []
    entries = [_entry_from_path(repo_root, p) for p in runs_dir.glob("*.json") if p.is_file()]
    # Newest first; ties broken by run_id for full determinism.
    entries.sort(key=lambda e: (e.started_at, e.run_id), reverse=True)
    if limit is not None and limit >= 0:
        entries = entries[:limit]
    return entries


def load_run(repo_root: Path, run_id: str, *, results_dirname: str = "ci_runs") -> dict[str, Any] | None:
    """Load a persisted run record as a raw dict (schema-drift tolerant)."""
    path = _default_runs_dir(repo_root, results_dirname) / f"{run_id}.json"
    if not path.is_file():
        # allow passing a bare stem that differs from run_id field
        for entry in list_runs(repo_root, results_dirname=results_dirname):
            if entry.run_id == run_id:
                path = Path(repo_root).resolve() / entry.path
                break
        else:
            return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def latest_run(repo_root: Path, *, results_dirname: str = "ci_runs") -> CIRunIndexEntry | None:
    runs = list_runs(repo_root, results_dirname=results_dirname, limit=1)
    return runs[0] if runs else None


def latest_passing_run(
    repo_root: Path, *, results_dirname: str = "ci_runs"
) -> CIRunIndexEntry | None:
    for entry in list_runs(repo_root, results_dirname=results_dirname):
        if entry.readable and entry.final_verdict in PASSING_VERDICTS:
            return entry
    return None


@dataclass
class CIRunComparison:
    schema_version: str = CI_SCHEMA_VERSION
    ci_policy_version: str = CI_POLICY_VERSION
    base_run_id: str = ""
    head_run_id: str = ""
    base_verdict: str = ""
    head_verdict: str = ""
    new_failure_classes: list[str] = field(default_factory=list)
    resolved_failure_classes: list[str] = field(default_factory=list)
    unchanged_failure_classes: list[str] = field(default_factory=list)
    tests_failed_delta: int | None = None
    regressed: bool = False
    improved: bool = False
    verdict_changed: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ci_policy_version": self.ci_policy_version,
            "base_run_id": self.base_run_id,
            "head_run_id": self.head_run_id,
            "base_verdict": self.base_verdict,
            "head_verdict": self.head_verdict,
            "new_failure_classes": list(self.new_failure_classes),
            "resolved_failure_classes": list(self.resolved_failure_classes),
            "unchanged_failure_classes": list(self.unchanged_failure_classes),
            "tests_failed_delta": self.tests_failed_delta,
            "regressed": self.regressed,
            "improved": self.improved,
            "verdict_changed": self.verdict_changed,
            "summary": self.summary,
        }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def compare_runs(base: dict[str, Any], head: dict[str, Any]) -> CIRunComparison:
    """Deterministically compare two CI run records (base = older, head = newer)."""
    base_fc = {str(f) for f in (base.get("failure_classes") or [])}
    head_fc = {str(f) for f in (head.get("failure_classes") or [])}
    base_verdict = str(base.get("final_verdict", ""))
    head_verdict = str(head.get("final_verdict", ""))

    new_fc = sorted(head_fc - base_fc)
    resolved_fc = sorted(base_fc - head_fc)
    unchanged_fc = sorted(base_fc & head_fc)

    base_failed = _int_or_none(base.get("tests_failed"))
    head_failed = _int_or_none(head.get("tests_failed"))
    delta: int | None = None
    if base_failed is not None and head_failed is not None:
        delta = head_failed - base_failed

    base_ok = base_verdict in PASSING_VERDICTS
    head_ok = head_verdict in PASSING_VERDICTS
    regressed = bool(new_fc) or (base_ok and not head_ok) or (delta is not None and delta > 0)
    improved = (not regressed) and (bool(resolved_fc) or (not base_ok and head_ok) or (delta is not None and delta < 0))

    cmp = CIRunComparison(
        base_run_id=str(base.get("run_id", "")),
        head_run_id=str(head.get("run_id", "")),
        base_verdict=base_verdict,
        head_verdict=head_verdict,
        new_failure_classes=new_fc,
        resolved_failure_classes=resolved_fc,
        unchanged_failure_classes=unchanged_fc,
        tests_failed_delta=delta,
        regressed=regressed,
        improved=improved,
        verdict_changed=base_verdict != head_verdict,
    )
    if regressed:
        cmp.summary = (
            f"REGRESSION: {base_verdict} -> {head_verdict}; "
            f"new failure classes: {new_fc or 'none'}"
        )
    elif improved:
        cmp.summary = (
            f"IMPROVED: {base_verdict} -> {head_verdict}; "
            f"resolved: {resolved_fc or 'none'}"
        )
    else:
        cmp.summary = f"NO CHANGE: {head_verdict} (failure classes stable)"
    return cmp


def compare_to_previous(
    repo_root: Path, *, results_dirname: str = "ci_runs"
) -> CIRunComparison | None:
    """Compare the two most recent runs (previous vs latest)."""
    runs = list_runs(repo_root, results_dirname=results_dirname, limit=2)
    if len(runs) < 2:
        return None
    head = load_run(repo_root, runs[0].run_id, results_dirname=results_dirname)
    base = load_run(repo_root, runs[1].run_id, results_dirname=results_dirname)
    if head is None or base is None:
        return None
    return compare_runs(base, head)
