"""YAML task persistence under workspace/active and workspace/completed."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import Task, TaskStatus, utc_now_iso
from .validation import ValidationError, apply_status_transition, validate_task_dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class TaskStore:
    def __init__(self, workspace_root: Path | None = None) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.active_dir = base / "active"
        self.completed_dir = base / "completed"
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, task_id: str, *, completed: bool = False) -> Path:
        folder = self.completed_dir if completed else self.active_dir
        return folder / f"{task_id}.yaml"

    def exists(self, task_id: str) -> bool:
        return self._path_for(task_id).exists() or self._path_for(task_id, completed=True).exists()

    def save(self, task: Task) -> Path:
        validate_task_dict(task.to_dict())
        completed = task.status is TaskStatus.COMPLETED
        path = self._path_for(task.id, completed=completed)
        # Remove from the other folder if moving.
        other = self._path_for(task.id, completed=not completed)
        if other.exists() and other != path:
            other.unlink()
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(task.to_dict(), fh, sort_keys=False)
        return path

    def load(self, task_id: str) -> Task:
        for completed in (False, True):
            path = self._path_for(task_id, completed=completed)
            if path.exists():
                with path.open(encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                return validate_task_dict(data)
        raise ValidationError(f"Task not found: {task_id}")

    def list_tasks(self, *, include_completed: bool = True) -> list[Task]:
        tasks: list[Task] = []
        dirs = [self.active_dir]
        if include_completed:
            dirs.append(self.completed_dir)
        for folder in dirs:
            for path in sorted(folder.glob("*.yaml")):
                with path.open(encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                tasks.append(validate_task_dict(data))
        return tasks

    def create(self, data: dict) -> Task:
        payload = dict(data)
        payload.setdefault("status", TaskStatus.DRAFT.value)
        payload.setdefault("created_at", utc_now_iso())
        payload.setdefault("updated_at", utc_now_iso())
        task = validate_task_dict(payload)
        if self.exists(task.id):
            raise ValidationError(f"Task already exists: {task.id}")
        self.save(task)
        return task

    def transition(self, task_id: str, new_status: TaskStatus) -> Task:
        task = self.load(task_id)
        updated = apply_status_transition(task, new_status)
        self.save(updated)
        return updated

    def update(self, task: Task) -> Task:
        if not self.exists(task.id):
            raise ValidationError(f"Task not found: {task.id}")
        data = task.to_dict()
        data["updated_at"] = utc_now_iso()
        updated = validate_task_dict(data)
        self.save(updated)
        return updated
