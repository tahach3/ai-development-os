"""Task store lifecycle persistence tests."""

from pathlib import Path

import pytest

from ai_dev_os.models import TaskStatus
from ai_dev_os.task_store import TaskStore
from ai_dev_os.validation import ValidationError


def test_create_load_transition(tmp_path: Path):
    store = TaskStore(tmp_path)
    task = store.create(
        {
            "id": "store1",
            "title": "Persist",
            "description": "Save me",
            "project_id": "demo",
            "task_type": "feature",
            "complexity": "normal",
            "risk_level": "low",
        }
    )
    assert store.load("store1").id == "store1"
    updated = store.transition("store1", TaskStatus.READY_FOR_PLANNING)
    assert updated.status is TaskStatus.READY_FOR_PLANNING
    with pytest.raises(ValidationError):
        store.transition("store1", TaskStatus.COMPLETED)
    # Move to completed via legal chain (abbreviated using blocked recovery not needed)
    for status in (
        TaskStatus.PLANNED,
        TaskStatus.APPROVED_FOR_IMPLEMENTATION,
        TaskStatus.IMPLEMENTING,
        TaskStatus.VALIDATING,
        TaskStatus.READY_FOR_REVIEW,
        TaskStatus.REVIEW_PASSED,
        TaskStatus.READY_TO_COMMIT,
        TaskStatus.COMPLETED,
    ):
        store.transition("store1", status)
    assert (tmp_path / "completed" / "store1.yaml").exists()
    assert not (tmp_path / "active" / "store1.yaml").exists()


def test_duplicate_create_rejected(tmp_path: Path):
    store = TaskStore(tmp_path)
    payload = {
        "id": "dup",
        "title": "A",
        "description": "B",
        "project_id": "demo",
        "task_type": "docs",
        "complexity": "small",
        "risk_level": "low",
    }
    store.create(payload)
    with pytest.raises(ValidationError, match="already exists"):
        store.create(payload)
