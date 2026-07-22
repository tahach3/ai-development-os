"""Behavioral metrics — recommendations only, never auto-rewrite rules."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .models import BehavioralRecommendation, BehavioralReport, Complexity, Task, utc_now_iso


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ci_aggregates_from_run(ci_run: Any | None) -> dict[str, Any]:
    if ci_run is None:
        return {}
    data = ci_run.to_dict() if hasattr(ci_run, "to_dict") else dict(ci_run)
    failed_stages = [
        s.get("stage_name")
        for s in (data.get("stages") or [])
        if s.get("validation_status") in {"failed", "timeout", "blocked", "error"}
        or s.get("blocker")
    ]
    return {
        "run_id": data.get("run_id"),
        "final_verdict": data.get("final_verdict"),
        "tests_passed": data.get("tests_passed"),
        "tests_failed": data.get("tests_failed"),
        "tests_skipped": data.get("tests_skipped"),
        "failed_stages": failed_stages,
        "failure_classes": list(data.get("failure_classes") or []),
        "human_review_required": bool(data.get("human_review_required")),
        "provider_mode": "not_invoked_by_ci",
    }


def _orch_aggregates(summaries: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not summaries:
        return {}
    stop_reasons: Counter[str] = Counter()
    repair_total = 0
    provider_modes: Counter[str] = Counter()
    human_review = 0
    for row in summaries:
        stop_reasons[str(row.get("stop_reason") or row.get("state") or "unknown")] += 1
        repair_total += int(row.get("repair_round_count") or row.get("repair_count") or 0)
        mode = row.get("invocation_mode") or row.get("provider_mode") or "unknown"
        provider_modes[str(mode)] += 1
        if str(row.get("state")) == "human_review_required" or row.get(
            "human_action_requirement"
        ):
            human_review += 1
    return {
        "orchestration_count": len(summaries),
        "repair_rounds_total": repair_total,
        "stop_reason_counts": dict(sorted(stop_reasons.items())),
        "provider_mode_counts": dict(sorted(provider_modes.items())),
        "human_review_count": human_review,
    }


def generate_behavioral_report(
    tasks: list[Task],
    *,
    ci_run: Any | None = None,
    orchestration_summaries: list[dict[str, Any]] | None = None,
) -> BehavioralReport:
    status_counts = Counter(t.status.value for t in tasks)
    routing_counts = Counter(
        (t.assigned_role.value if t.assigned_role else "unassigned") for t in tasks
    )
    risk_counts = Counter(t.risk_level.value for t in tasks)
    complexity_counts = Counter(t.complexity.value for t in tasks)

    recommendations: list[str] = []
    if status_counts.get("blocked", 0) >= 2:
        recommendations.append(
            "Multiple tasks are blocked — review blocked_reason fields and clear gates manually."
        )
    if status_counts.get("review_failed", 0) > 0:
        recommendations.append(
            "Review failures present — prefer Codex independent review before re-implementation."
        )
    if routing_counts.get("unassigned", 0) > 0:
        recommendations.append(
            "Some tasks are unassigned — run route-task before prepare-handoff."
        )
    high_risk = risk_counts.get("high", 0) + risk_counts.get("critical", 0)
    if high_risk and routing_counts.get("cursor", 0) > routing_counts.get("claude", 0):
        recommendations.append(
            "High/critical risk volume is significant — consider routing more of those to Claude."
        )

    ci_agg = _ci_aggregates_from_run(ci_run)
    orch_agg = _orch_aggregates(orchestration_summaries)
    aggregates = {**ci_agg, **{f"orch_{k}": v for k, v in orch_agg.items()}}

    if ci_agg.get("tests_failed"):
        recommendations.append(
            "CI reported test failures — treat as merge blockers until green."
        )
    if ci_agg.get("failed_stages"):
        recommendations.append(
            "CI validation stages failed — inspect sanitized stage summaries before merge."
        )
    if ci_agg.get("human_review_required") or orch_agg.get("human_review_count"):
        recommendations.append(
            "Human-review requirements present — do not auto-route or auto-merge."
        )
    if orch_agg.get("repair_rounds_total", 0) >= 3:
        recommendations.append(
            "Elevated repair-round volume — review stalemate evidence and plan quality."
        )

    if not recommendations:
        recommendations.append(
            "No strong behavioral signals; continue manual routing and review discipline."
        )

    avg_band = None
    if complexity_counts:
        avg_band = complexity_counts.most_common(1)[0][0]
        try:
            Complexity(avg_band)
        except ValueError:
            avg_band = None

    records = [
        BehavioralRecommendation(id=f"rec_{i+1:03d}", text=text, version="4a.1")
        for i, text in enumerate(recommendations)
    ]

    return BehavioralReport(
        generated_at=utc_now_iso(),
        task_count=len(tasks),
        status_counts=dict(sorted(status_counts.items())),
        routing_counts=dict(sorted(routing_counts.items())),
        risk_counts=dict(sorted(risk_counts.items())),
        avg_complexity_band=avg_band,
        recommendations=recommendations,
        auto_rewrite_rules=False,
        schema_version="4a.1",
        ci_aggregates=aggregates,
        recommendation_records=records,
    )


def write_behavioral_report(
    report: BehavioralReport,
    output_dir: Path | None = None,
) -> Path:
    out_dir = output_dir or (_repo_root() / "workspace" / "behavioral_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.replace(":", "").replace("+00:00", "Z")
    path = out_dir / f"behavioral_{stamp}.json"
    payload = report.to_dict()
    # Hard guarantee: never enable auto rewrite.
    payload["auto_rewrite_rules"] = False
    for rec in payload.get("recommendation_records") or []:
        rec["active"] = False
        rec["status"] = "proposed"
        rec["requires_human_approval"] = True
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def render_behavioral_markdown(report: BehavioralReport) -> str:
    lines = [
        "# Behavioral Report",
        "",
        f"Generated: {report.generated_at}",
        f"Schema: {report.schema_version}",
        "",
        f"## Task count: {report.task_count}",
        "",
        "### Status counts",
    ]
    for key, value in report.status_counts.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("### Routing counts")
    for key, value in report.routing_counts.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("### Risk counts")
    for key, value in report.risk_counts.items():
        lines.append(f"- {key}: {value}")
    if report.ci_aggregates:
        lines.extend(["", "### CI / orchestration aggregates (sanitized)"])
        for key, value in sorted(report.ci_aggregates.items()):
            lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            f"Most common complexity band: {report.avg_complexity_band or 'n/a'}",
            "",
            "## Recommendations (proposed / inactive until human approval)",
        ]
    )
    for rec in report.recommendation_records or []:
        lines.append(
            f"- [{rec.id}] {rec.text} (version={rec.version}, active={rec.active})"
        )
    if not report.recommendation_records:
        for rec in report.recommendations:
            lines.append(f"- {rec}")
    lines.extend(["", "auto_rewrite_rules: false", ""])
    return "\n".join(lines)
