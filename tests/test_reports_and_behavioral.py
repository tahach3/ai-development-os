"""Reports, budgets recording, adapters, behavioral metrics."""

from pathlib import Path

from ai_dev_os.adapters import get_adapter
from ai_dev_os.behavioral_metrics import generate_behavioral_report, write_behavioral_report
from ai_dev_os.models import (
    Complexity,
    ImplementationReport,
    ModelRole,
    ReportOutcome,
    ReviewReport,
    ReviewVerdict,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
    TokenUsage,
    TokenUsageMode,
)
from ai_dev_os.report_store import ReportStore
from ai_dev_os.routing import apply_routing, get_budget_limits


def test_report_store_and_review_status(tmp_path: Path):
    store = ReportStore(tmp_path)
    impl = ImplementationReport(
        task_id="r1",
        summary="done",
        files_changed=["a.py"],
        tests_run=["pytest -q"],
        outcome=ReportOutcome.SUCCESS,
        token_usage=TokenUsage(mode=TokenUsageMode.UNAVAILABLE),
    )
    store.save_implementation(impl)
    review = ReviewReport(
        task_id="r1",
        reviewer_role=ModelRole.CODEX,
        verdict=ReviewVerdict.PASS,
    )
    store.save_review(review)
    assert store.latest_review("r1").verdict is ReviewVerdict.PASS
    assert store.list_implementation("r1")[0].token_usage.mode is TokenUsageMode.UNAVAILABLE


def test_budget_bands_exist():
    for band in Complexity:
        limits = get_budget_limits(band)
        assert limits["max_input_tokens"] > 0
        assert limits["max_output_tokens"] > 0


def test_manual_adapters(tmp_path: Path):
    task = apply_routing(
        Task(
            id="h1",
            title="Handoff",
            description="Manual only",
            project_id="demo",
            task_type=TaskType.FEATURE,
            complexity=Complexity.NORMAL,
            risk_level=RiskLevel.LOW,
        )
    )
    for role in ("claude", "cursor", "codex"):
        result = get_adapter(role).prepare_handoff(task, tmp_path, tmp_path / role)
        assert result.automation_status == "manual_handoff_required"
        assert result.handoff_path.exists()
        text = result.handoff_path.read_text(encoding="utf-8")
        assert "manual_handoff_required" in text


def test_behavioral_recommendations_no_auto_rewrite(tmp_path: Path):
    tasks = [
        Task(
            id="b1",
            title="A",
            description="B",
            project_id="demo",
            task_type=TaskType.FEATURE,
            complexity=Complexity.NORMAL,
            risk_level=RiskLevel.HIGH,
            status=TaskStatus.BLOCKED,
            blocked_reason="waiting",
        ),
        Task(
            id="b2",
            title="A",
            description="B",
            project_id="demo",
            task_type=TaskType.FEATURE,
            complexity=Complexity.NORMAL,
            risk_level=RiskLevel.HIGH,
            status=TaskStatus.BLOCKED,
            blocked_reason="waiting",
        ),
    ]
    report = generate_behavioral_report(tasks)
    assert report.auto_rewrite_rules is False
    assert report.to_dict()["auto_rewrite_rules"] is False
    assert any("blocked" in r.lower() for r in report.recommendations)
    path = write_behavioral_report(report, tmp_path)
    assert path.exists()
