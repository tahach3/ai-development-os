"""Validation and lifecycle transition tests."""

import pytest

from ai_dev_os.models import Task, TaskStatus, TaskType, Complexity, RiskLevel
from ai_dev_os.validation import (
    ValidationError,
    apply_status_transition,
    validate_no_illegal_jump,
    validate_task_dict,
)


def _base(**overrides):
    data = {
        "id": "t1",
        "title": "Title",
        "description": "Desc",
        "project_id": "demo",
        "task_type": "feature",
        "complexity": "normal",
        "risk_level": "medium",
    }
    data.update(overrides)
    return data


def test_validate_missing_fields():
    with pytest.raises(ValidationError, match="Missing required"):
        validate_task_dict({"id": "x"})


def test_validate_invalid_enum():
    with pytest.raises(ValidationError):
        validate_task_dict(_base(task_type="nope"))


def test_reject_draft_to_completed_jump():
    with pytest.raises(ValidationError, match="Illegal jump|Invalid lifecycle"):
        validate_no_illegal_jump(TaskStatus.DRAFT, TaskStatus.COMPLETED)


def test_valid_transition_chain():
    task = Task.from_dict(_base())
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    assert task.status is TaskStatus.PLANNED


def test_allowed_prohibited_conflict():
    with pytest.raises(ValidationError, match="conflicts"):
        validate_task_dict(
            _base(
                allowed_paths=[r"C:\proj\src\a.py"],
                prohibited_paths=[r"C:\proj\src"],
            )
        )


def test_happy_path_task():
    task = validate_task_dict(_base(acceptance_criteria=["works"]))
    assert task.task_type is TaskType.FEATURE
    assert task.complexity is Complexity.NORMAL
    assert task.risk_level is RiskLevel.MEDIUM
