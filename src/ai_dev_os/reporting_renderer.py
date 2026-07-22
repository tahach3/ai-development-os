"""Deterministic Markdown renderer for Round 4C reports."""

from __future__ import annotations

from typing import Any

from .reporting_constants import RENDERER_VERSION
from .reporting_models import CanonicalReportSnapshot, DetailLevel, ReportAudience
from .reporting_redaction import strip_ansi


def _md_escape_cell(value: Any) -> str:
    text = strip_ansi(str(value)).replace("|", "\\|").replace("\n", " ")
    return text


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_escape_cell(c) for c in row) + " |")
    return "\n".join(lines)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {strip_ansi(i)}" for i in items if i)


def _render_section(section_id: str, title: str, content: dict[str, Any], *, collapsed: bool) -> str:
    parts = [f"## {title}"]
    if collapsed:
        parts.append("_Collapsed summary_")
    if section_id == "status_glance":
        parts.append(
            f"- Report status: **{content.get('report_status')}**\n"
            f"- Outcome: {content.get('outcome')}\n"
            f"- Final verdict: {content.get('final_verdict')}"
        )
        blockers = content.get("blockers") or []
        if blockers:
            parts.append("Blockers:\n" + _bullets([str(b) for b in blockers]))
    elif section_id == "executive_summary":
        parts.append(content.get("result_paragraph") or "")
        parts.append(f"- Completion confidence: {content.get('completion_confidence')}")
        parts.append(f"- Validation: {content.get('validation_summary')}")
        parts.append(f"- Highest remaining risk: {content.get('highest_remaining_risk')}")
        parts.append(f"- Required human action: {content.get('required_human_action')}")
        parts.append(f"- Next step: {content.get('next_recommended_step')}")
        changes = content.get("key_changes") or []
        if changes:
            parts.append("Key changes:\n" + _bullets([str(c) for c in changes]))
    elif section_id == "acceptance":
        rows = content.get("rows") or []
        table_rows = [
            [
                r.get("criterion_id"),
                r.get("status"),
                r.get("claim_status"),
                ",".join(r.get("evidence_ids") or []),
            ]
            for r in rows
        ]
        tbl = _table(["ID", "Status", "Claim", "Evidence"], table_rows)
        if tbl:
            parts.append(tbl)
    elif section_id == "tests":
        for k in (
            "scope",
            "summary",
            "passed_count",
            "failed_count",
            "skipped_count",
            "xfailed_count",
            "coverage_percent",
            "coverage_source",
        ):
            if k in content and content[k] is not None:
                parts.append(f"- {k}: {content[k]}")
        failing = content.get("failing_tests") or []
        if failing:
            parts.append("Failing tests:\n" + _bullets([str(x) for x in failing]))
        if content.get("coverage_percent") is None and "coverage" not in content:
            parts.append("- coverage: unavailable (not measured)")
    elif section_id == "ci":
        for k, v in sorted(content.items(), key=lambda kv: kv[0]):
            if k == "stages" and isinstance(v, list):
                continue
            parts.append(f"- {k}: {v}")
    elif section_id == "security_deps":
        parts.append(f"- Conclusion: {content.get('conclusion')}")
        parts.append(f"- Note: {content.get('note')}")
        dep = content.get("dependencies") or {}
        if dep:
            parts.append(f"- vulnerability_scan: {dep.get('vulnerability_scan', 'unavailable')}")
            if dep.get("policy_verdict"):
                parts.append(f"- dependency_policy: {dep.get('policy_verdict')}")
        findings = content.get("findings") or []
        if findings:
            parts.append(
                _table(
                    ["ID", "Severity", "Title", "Blocking"],
                    [
                        [f.get("finding_id"), f.get("severity"), f.get("title"), f.get("blocking")]
                        for f in findings
                    ],
                )
            )
    elif section_id == "usage":
        fields = content.get("fields") or []
        parts.append(
            _table(
                ["Name", "State", "Value"],
                [[f.get("name"), f.get("state"), f.get("value")] for f in fields],
            )
            or "- Usage unavailable"
        )
    elif section_id == "risks":
        risks = content.get("risks") or []
        if risks:
            parts.append(
                _table(
                    ["ID", "Severity", "Blocking", "Description"],
                    [
                        [r.get("risk_id"), r.get("severity"), r.get("blocking"), r.get("description")]
                        for r in risks
                    ],
                )
            )
        blockers = content.get("blockers") or []
        if blockers:
            parts.append("Blockers:\n" + _bullets([str(b) for b in blockers]))
        conflicts = content.get("unresolved_conflicts") or []
        if conflicts:
            parts.append("Unresolved conflicts:\n" + _bullets([c.get("description", str(c)) for c in conflicts]))
    elif section_id == "next_action":
        actions = content.get("actions") or []
        parts.append(
            _bullets(
                [
                    f"[{a.get('action_type')}]{' (required)' if a.get('required') else ''} {a.get('text')}"
                    for a in actions
                ]
            )
            or "- No next action recorded"
        )
    elif section_id == "audit_appendix":
        parts.append(f"- schema_version: {content.get('schema_version')}")
        pv = content.get("policy_versions") or {}
        for k in sorted(pv):
            parts.append(f"- policy.{k}: {pv[k]}")
        bindings = content.get("source_bindings") or {}
        for k in sorted(bindings):
            parts.append(f"- binding.{k}: {bindings[k]}")
    elif section_id == "evidence_summary":
        parts.append(f"- evidence_count: {content.get('count')}")
        ids = content.get("ids") or []
        if ids:
            parts.append("Evidence IDs:\n" + _bullets([str(i) for i in ids]))
    elif section_id == "provider_orch":
        for k in sorted(content.keys()):
            parts.append(f"- {k}: {content[k]}")
        if content.get("execution_mode") == "simulation" or content.get("simulation_label"):
            parts.append("- Label: simulation (not a live model result)")
    elif section_id == "failures_repairs":
        repairs = content.get("repairs") or []
        if repairs:
            parts.append(f"- repair_rounds: {len(repairs)}")
            for r in repairs:
                parts.append(
                    f"- round {r.get('repair_round_number') or r.get('round_number')}: "
                    f"{r.get('final_outcome') or r.get('result')}"
                )
        rcs = content.get("root_causes") or []
        for rc in rcs:
            parts.append(
                f"- root_cause {rc.get('root_cause_id')}: confidence={rc.get('confidence')}"
            )
    elif section_id == "changes":
        if "added_count" in content:
            parts.append(
                f"- added={content.get('added_count')}, "
                f"modified={content.get('modified_count')}, "
                f"deleted={content.get('deleted_count')}"
            )
            if content.get("documentation_only"):
                parts.append("- classification: documentation-only")
        else:
            for key in ("files_added", "files_modified", "files_deleted"):
                files = content.get(key) or []
                if files:
                    parts.append(f"{key}:\n" + _bullets([str(f) for f in files]))
            if content.get("documentation_only"):
                parts.append("- classification: documentation-only")
    else:
        # Generic structured dump (stable key order), skip empties
        for k in sorted(content.keys()):
            v = content[k]
            if v in (None, "", [], {}):
                continue
            if isinstance(v, (list, dict)):
                parts.append(f"- {k}: {v}")
            else:
                parts.append(f"- {k}: {v}")

    body = "\n\n".join(p for p in parts[1:] if p)
    if not body.strip():
        return ""
    return parts[0] + "\n\n" + body + "\n"


def render_markdown(snapshot: CanonicalReportSnapshot) -> str:
    title = (
        f"# Report {snapshot.report_id} "
        f"({snapshot.audience.value} / {snapshot.detail_level.value})"
    )
    header = [
        title,
        "",
        f"- renderer_version: {RENDERER_VERSION}",
        f"- report_status: {snapshot.report_status.value}",
        f"- task_id: {snapshot.task_id}",
        f"- project_id: {snapshot.project_id}",
        f"- report_fingerprint: {snapshot.report_fingerprint}",
        f"- source_set_fingerprint: {snapshot.source_set_fingerprint}",
        "",
    ]
    seen: set[str] = set()
    sections_out: list[str] = []
    for section in snapshot.section_records:
        if not section.included:
            continue
        if section.section_id in seen:
            continue
        seen.add(section.section_id)
        rendered = _render_section(
            section.section_id,
            section.title,
            section.content,
            collapsed=section.collapsed,
        )
        if rendered:
            sections_out.append(rendered)
    return "\n".join(header) + "\n".join(sections_out).rstrip() + "\n"


def audience_title(audience: ReportAudience, detail: DetailLevel) -> str:
    return f"{audience.value}:{detail.value}"
