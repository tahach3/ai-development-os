"""Repair-round tracking with configurable maximum (Ralphex-inspired)."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import RepairRound, Task, TaskStatus, utc_now_iso
from .task_store import TaskStore
from .validation import ValidationError, apply_status_transition


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_repair_config_path() -> Path:
    return _repo_root() / "config" / "repair_rounds.yaml"


def load_max_repair_rounds(config_path: Path | None = None) -> int:
    path = config_path or default_repair_config_path()
    if not path.exists():
        return 3
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    value = int(data.get("max_repair_rounds", 3))
    if value < 1:
        raise ValidationError("max_repair_rounds must be >= 1")
    return value


class RepairRoundStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.dir = base / "repair_rounds"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.dir / f"{task_id}.yaml"

    def list_rounds(self, task_id: str) -> list[RepairRound]:
        path = self._path(task_id)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        items = data.get("rounds") or []
        return [RepairRound.from_dict(item) for item in items]

    def count(self, task_id: str) -> int:
        return len(self.list_rounds(task_id))

    def save_rounds(self, task_id: str, rounds: list[RepairRound]) -> Path:
        path = self._path(task_id)
        payload = {"task_id": task_id, "rounds": [r.to_dict() for r in rounds]}
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, sort_keys=False)
        return path

    def record(
        self,
        round_data: RepairRound,
        *,
        task_store: TaskStore,
        max_rounds: int | None = None,
    ) -> tuple[RepairRound, Task]:
        limit = max_rounds if max_rounds is not None else load_max_repair_rounds()
        task = task_store.load(round_data.task_id)
        existing = self.list_rounds(round_data.task_id)
        next_num = len(existing) + 1
        if round_data.round_number <= 0:
            round_data.round_number = next_num
        if round_data.round_number != next_num:
            raise ValidationError(
                f"Repair round number must be {next_num} (got {round_data.round_number})"
            )
        if not round_data.created_at:
            round_data.created_at = utc_now_iso()

        if next_num > limit:
            task.blocked_reason = (
                f"Repair-round limit exceeded ({limit}); human review required"
            )
            task = apply_status_transition(task, TaskStatus.BLOCKED)
            task_store.update(task)
            raise ValidationError(task.blocked_reason)

        existing.append(round_data)
        self.save_rounds(round_data.task_id, existing)

        meta = dict(task.metadata)
        meta["repair_round_count"] = len(existing)
        task.metadata = meta

        if next_num >= limit and round_data.result in ("failed", "blocked", "stalemate"):
            task.blocked_reason = (
                f"Repair-round limit reached ({limit}) with result={round_data.result}; "
                "human review required"
            )
            task = apply_status_transition(task, TaskStatus.BLOCKED)
        elif task.status is TaskStatus.REVIEW_FAILED:
            # Return to implementation for another repair attempt.
            task = apply_status_transition(task, TaskStatus.IMPLEMENTING)

        if round_data.reapproval_required or round_data.scope_changed:
            # Scope change requires returning toward planning/approval.
            if task.status not in (TaskStatus.BLOCKED, TaskStatus.CANCELLED):
                task.blocked_reason = (
                    task.blocked_reason
                    or "Scope changed during repair; reapproval required"
                )
                if task.status is not TaskStatus.BLOCKED:
                    task = apply_status_transition(task, TaskStatus.BLOCKED)

        task_store.update(task)
        return round_data, task
