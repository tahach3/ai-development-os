"""Tests for core task models and lifecycle map."""

from ai_dev_os.models import (
    LIFECYCLE_TRANSITIONS,
    Complexity,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
    TokenUsage,
    TokenUsageMode,
)


def test_task_roundtrip():
    task = Task(
        id="t1",
        title="Title",
        description="Desc",
        project_id="demo",
        task_type=TaskType.FEATURE,
        complexity=Complexity.NORMAL,
        risk_level=RiskLevel.MEDIUM,
    )
    restored = Task.from_dict(task.to_dict())
    assert restored.id == "t1"
    assert restored.task_type is TaskType.FEATURE
    assert restored.status is TaskStatus.DRAFT


def test_token_usage_unavailable_clears_counts():
    usage = TokenUsage.from_dict(
        {
            "mode": "unavailable",
            "input_tokens": 99,
            "output_tokens": 88,
        }
    )
    assert usage.mode is TokenUsageMode.UNAVAILABLE
    assert usage.input_tokens is None
    assert usage.output_tokens is None


def test_lifecycle_has_no_draft_to_completed():
    allowed = LIFECYCLE_TRANSITIONS[TaskStatus.DRAFT]
    assert TaskStatus.COMPLETED not in allowed
    assert TaskStatus.READY_FOR_PLANNING in allowed
