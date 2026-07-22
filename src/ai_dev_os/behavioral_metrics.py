"""Behavioral metrics — recommendations only, never auto-rewrite rules."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .models import BehavioralReport, Complexity, Task, utc_now_iso


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def generate_behavioral_report(tasks: list[Task]) -> BehavioralReport:
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
    if not recommendations:
        recommendations.append(
            "No strong behavioral signals; continue manual routing and review discipline."
        )

    avg_band = None
    if complexity_counts:
        # Deterministic: pick the most common complexity band.
        avg_band = complexity_counts.most_common(1)[0][0]
        # Validate against known bands.
        try:
            Complexity(avg_band)
        except ValueError:
            avg_band = None

    return BehavioralReport(
        generated_at=utc_now_iso(),
        task_count=len(tasks),
        status_counts=dict(sorted(status_counts.items())),
        routing_counts=dict(sorted(routing_counts.items())),
        risk_counts=dict(sorted(risk_counts.items())),
        avg_complexity_band=avg_band,
        recommendations=recommendations,
        auto_rewrite_rules=False,
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
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def render_behavioral_markdown(report: BehavioralReport) -> str:
    lines = [
        "# Behavioral Report",
        "",
        f"Generated: {report.generated_at}",
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
    lines.extend(
        [
            "",
            f"Most common complexity band: {report.avg_complexity_band or 'n/a'}",
            "",
            "## Recommendations (manual only — no auto rule rewrite)",
        ]
    )
    for rec in report.recommendations:
        lines.append(f"- {rec}")
    lines.extend(["", "auto_rewrite_rules: false", ""])
    return "\n".join(lines)
