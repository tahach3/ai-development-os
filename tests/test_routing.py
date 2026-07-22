"""Deterministic routing and token budget tests."""

from ai_dev_os.models import Complexity, ModelRole, RiskLevel, Task, TaskType
from ai_dev_os.routing import apply_routing, get_budget_limits, route_task, select_token_budget_band


def _task(**kwargs) -> Task:
    base = dict(
        id="t1",
        title="T",
        description="D",
        project_id="demo",
        task_type=TaskType.FEATURE,
        complexity=Complexity.NORMAL,
        risk_level=RiskLevel.MEDIUM,
    )
    base.update(kwargs)
    return Task(**base)


def test_high_risk_routes_to_claude():
    decision = route_task(_task(risk_level=RiskLevel.HIGH))
    assert decision.role is ModelRole.CLAUDE
    assert "risk" in decision.explanation.lower() or "High" in decision.explanation


def test_review_routes_to_codex():
    decision = route_task(_task(task_type=TaskType.INDEPENDENT_REVIEW))
    assert decision.role is ModelRole.CODEX


def test_ui_routes_to_cursor():
    decision = route_task(_task(task_type=TaskType.UI, complexity=Complexity.SMALL))
    assert decision.role is ModelRole.CURSOR


def test_default_normal_feature_to_cursor():
    decision = route_task(_task())
    assert decision.role is ModelRole.CURSOR


def test_budget_band_elevates_on_critical_risk():
    band = select_token_budget_band(_task(risk_level=RiskLevel.CRITICAL, complexity=Complexity.SMALL))
    assert band is Complexity.HIGH_RISK
    limits = get_budget_limits(band)
    assert limits["max_input_tokens"] > 0
    assert limits["band"] == "high_risk"


def test_apply_routing_persists_explanation():
    updated = apply_routing(_task(complexity=Complexity.COMPLEX))
    assert updated.assigned_role is ModelRole.CLAUDE
    assert updated.routing_explanation
    assert updated.token_budget_band is Complexity.COMPLEX
