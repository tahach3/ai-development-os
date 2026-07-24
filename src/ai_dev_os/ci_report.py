"""Round 4A hardening — deterministic human-readable CI report rendering.

Renders the JSON CI envelopes (`CIRun`, targeted runs, run comparisons) into a
stable Markdown summary that lists every field the Round 4A reporting contract
calls for: executed stages, per-stage duration, pass/fail, skipped stages,
failure reason, affected files, the command each stage ran, the persisted
artifact location, and the run's audit identifier.

Rendering is pure and deterministic — same envelope in, byte-identical Markdown
out — so it can be diffed, snapshotted, or attached to an audit record.
"""

from __future__ import annotations

from typing import Any

from .ci_models import CIRun, CIStageStatus


def _fmt_duration(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "0.000"


def render_ci_summary(run: CIRun, *, artifact_path: str | None = None) -> str:
    """Render a CIRun as deterministic Markdown."""
    lines: list[str] = []
    lines.append(f"# CI Run `{run.run_id}`")
    lines.append("")
    lines.append(f"- **Verdict:** `{run.final_verdict}`")
    lines.append(f"- **Trigger:** {run.trigger_type}")
    lines.append(f"- **State:** {run.state}")
    lines.append(f"- **Starting commit:** `{(run.starting_commit or '(none)')[:12]}`")
    if run.compared_base_commit:
        lines.append(f"- **Compared base:** `{run.compared_base_commit[:12]}`")
    lines.append(f"- **Duration:** {_fmt_duration(run.duration_seconds)}s")
    lines.append(
        "- **Tests:** "
        f"passed={run.tests_passed if run.tests_passed is not None else '-'} "
        f"failed={run.tests_failed if run.tests_failed is not None else '-'} "
        f"skipped={run.tests_skipped if run.tests_skipped is not None else '-'}"
    )
    lines.append(f"- **Policy decision:** {run.policy_decision}")
    lines.append(f"- **Human review required:** {str(run.human_review_required).lower()}")
    lines.append(f"- **Audit id:** `{run.run_id}`")
    lines.append(f"- **Artifact:** {artifact_path or '(not persisted)'}")
    if run.failure_classes:
        lines.append(f"- **Failure classes:** {', '.join(run.failure_classes)}")
    lines.append(f"- **Next action:** {run.next_action or '(none)'}")
    lines.append("")

    executed = [s for s in run.stages if s.validation_status != CIStageStatus.SKIPPED.value]
    skipped = [s for s in run.stages if s.validation_status == CIStageStatus.SKIPPED.value]

    lines.append("## Stages executed")
    lines.append("")
    lines.append("| # | Stage | Status | Duration(s) | Failure class | Command | Files |")
    lines.append("| - | ----- | ------ | ----------- | ------------- | ------- | ----- |")
    for idx, stage in enumerate(run.stages, start=1):
        lines.append(
            f"| {idx} | {stage.stage_name} | {stage.validation_status} | "
            f"{_fmt_duration(stage.duration_seconds)} | "
            f"{stage.failure_class} | `{stage.command_identity}` | "
            f"{len(stage.files_examined)} |"
        )
    lines.append("")

    failures = [
        s
        for s in run.stages
        if s.validation_status
        in {
            CIStageStatus.FAILED.value,
            CIStageStatus.TIMEOUT.value,
            CIStageStatus.BLOCKED.value,
            CIStageStatus.ERROR.value,
        }
    ]
    if failures:
        lines.append("## Failure reasons")
        lines.append("")
        for stage in failures:
            first_line = (stage.sanitized_output_summary or "").splitlines()
            reason = first_line[0] if first_line else "(no summary)"
            lines.append(f"- **{stage.stage_name}** (`{stage.failure_class}`): {reason}")
            if stage.files_examined:
                shown = ", ".join(stage.files_examined[:8])
                more = "" if len(stage.files_examined) <= 8 else f" (+{len(stage.files_examined) - 8} more)"
                lines.append(f"  - affected files: {shown}{more}")
            if stage.next_action:
                lines.append(f"  - next: {stage.next_action}")
        lines.append("")

    if skipped:
        lines.append("## Skipped stages")
        lines.append("")
        for stage in skipped:
            reason = stage.sanitized_output_summary or "skipped"
            lines.append(f"- {stage.stage_name}: {reason}")
        lines.append("")

    if run.sanitized_notes:
        lines.append("## Notes")
        lines.append("")
        for note in run.sanitized_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append(
        f"_Executed {len(executed)} stage(s); {len(skipped)} skipped; "
        f"{len(failures)} failing. No automatic merge or deploy._"
    )
    return "\n".join(lines) + "\n"


def render_boundary_summary(result: Any) -> str:
    """Render a BoundaryCheckResult (or its to_dict()) as deterministic Markdown."""
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    ok = bool(data.get("ok"))
    findings = list(data.get("findings") or [])
    failure_classes = list(data.get("failure_classes") or [])
    files_examined = list(data.get("files_examined") or [])

    lines: list[str] = []
    lines.append("# Boundary check")
    lines.append("")
    lines.append(f"- **OK:** {str(ok).lower()}")
    lines.append(f"- **Files examined:** {len(files_examined)}")
    lines.append(
        f"- **Failure classes:** {', '.join(failure_classes) if failure_classes else '(none)'}"
    )
    lines.append(f"- **Findings:** {len(findings)}")
    lines.append("")

    if findings:
        lines.append("## Findings")
        lines.append("")
        for finding in findings:
            path = finding.get("path", "") if isinstance(finding, dict) else finding.path
            project_id = (
                finding.get("project_id", "")
                if isinstance(finding, dict)
                else finding.project_id
            )
            reason = finding.get("reason", "") if isinstance(finding, dict) else finding.reason
            failure_class = (
                finding.get("failure_class", "")
                if isinstance(finding, dict)
                else finding.failure_class
            )
            detail = finding.get("detail", "") if isinstance(finding, dict) else finding.detail
            blocker = (
                finding.get("blocker", True)
                if isinstance(finding, dict)
                else getattr(finding, "blocker", True)
            )
            lines.append(
                f"- `{path}` ({project_id}): `{reason}` / `{failure_class}` — {detail} "
                f"[blocker={str(bool(blocker)).lower()}]"
            )
        lines.append("")

    if files_examined:
        lines.append("## Files examined")
        lines.append("")
        for path in files_examined:
            lines.append(f"- `{path}`")
        lines.append("")

    lines.append(
        f"_{len(findings)} finding(s); {len(files_examined)} file(s) examined. "
        f"No automatic merge or deploy._"
    )
    return "\n".join(lines) + "\n"


def render_validate_change_summary(summary: Any) -> str:
    """Render a PRValidationSummary (or its to_dict()) as deterministic Markdown."""
    data = summary.to_dict() if hasattr(summary, "to_dict") else dict(summary)
    findings = list(data.get("findings") or [])
    failure_classes = list(data.get("failure_classes") or [])
    files_examined = list(data.get("files_examined") or [])
    starting = data.get("starting_commit") or ""
    compared = data.get("compared_base_commit")
    run_id = data.get("run_id") or ""

    lines: list[str] = []
    lines.append(f"# Validate change `{run_id}`")
    lines.append("")
    lines.append(f"- **Verdict:** `{data.get('final_verdict', '')}`")
    lines.append(f"- **Trigger:** {data.get('trigger_type', '')}")
    lines.append(f"- **Policy decision:** {data.get('policy_decision', '')}")
    lines.append(f"- **Blocker:** {str(bool(data.get('blocker', False))).lower()}")
    lines.append(
        f"- **Human review required:** "
        f"{str(bool(data.get('human_review_required', False))).lower()}"
    )
    lines.append(f"- **Starting commit:** `{(starting or '(none)')[:12]}`")
    if compared:
        lines.append(f"- **Compared base:** `{str(compared)[:12]}`")
    else:
        lines.append("- **Compared base:** `(none)`")
    lines.append(f"- **Duration:** {_fmt_duration(data.get('duration_seconds', 0))}s")
    lines.append(f"- **Schema version:** {data.get('schema_version', '')}")
    lines.append(f"- **CI policy version:** {data.get('ci_policy_version', '')}")
    lines.append(f"- **Repository:** {data.get('repository_identity', '') or '(none)'}")
    if data.get("started_at"):
        lines.append(f"- **Started:** {data.get('started_at')}")
    if data.get("finished_at"):
        lines.append(f"- **Finished:** {data.get('finished_at')}")
    lines.append(f"- **Audit id:** `{run_id}`")
    lines.append(f"- **Next action:** {data.get('next_action') or '(none)'}")
    lines.append(f"- **Auto-approve:** {str(bool(data.get('auto_approve', False))).lower()}")
    lines.append(f"- **Auto-merge:** {str(bool(data.get('auto_merge', False))).lower()}")
    lines.append(f"- **Files examined:** {len(files_examined)}")
    lines.append(f"- **Findings:** {len(findings)}")
    lines.append("")

    if findings:
        lines.append("## Findings")
        lines.append("")
        for finding in findings:
            if isinstance(finding, dict):
                path = finding.get("path", "")
                category = finding.get("category", "")
                severity = finding.get("severity", "")
                failure_class = finding.get("failure_class", "")
                summary_text = finding.get("summary", "")
                blocker = finding.get("blocker", False)
                hrr = finding.get("human_review_required", False)
            else:
                path = finding.path
                category = finding.category
                severity = finding.severity
                failure_class = finding.failure_class
                summary_text = finding.summary
                blocker = finding.blocker
                hrr = finding.human_review_required
            lines.append(
                f"- `{path}` [{category}/{severity}] `{failure_class}`: {summary_text} "
                f"[blocker={str(bool(blocker)).lower()}, "
                f"human_review={str(bool(hrr)).lower()}]"
            )
        lines.append("")

    if failure_classes:
        lines.append("## Failure classes")
        lines.append("")
        for fc in failure_classes:
            lines.append(f"- {fc}")
        lines.append("")

    if files_examined:
        lines.append("## Files examined")
        lines.append("")
        for path in files_examined:
            lines.append(f"- `{path}`")
        lines.append("")

    blockers = sum(
        1
        for f in findings
        if (f.get("blocker") if isinstance(f, dict) else getattr(f, "blocker", False))
    )
    lines.append(
        f"_{len(findings)} finding(s); {blockers} blocker(s); "
        f"{len(files_examined)} file(s) examined. No automatic merge or approve._"
    )
    return "\n".join(lines) + "\n"


def render_comparison(cmp_dict: dict[str, Any]) -> str:
    """Render a CI run comparison dict as Markdown."""
    lines: list[str] = []
    lines.append("# CI run comparison")
    lines.append("")
    lines.append(f"- **Base:** `{cmp_dict.get('base_run_id', '')}` ({cmp_dict.get('base_verdict', '')})")
    lines.append(f"- **Head:** `{cmp_dict.get('head_run_id', '')}` ({cmp_dict.get('head_verdict', '')})")
    lines.append(f"- **Regressed:** {str(cmp_dict.get('regressed', False)).lower()}")
    lines.append(f"- **Improved:** {str(cmp_dict.get('improved', False)).lower()}")
    delta = cmp_dict.get("tests_failed_delta")
    lines.append(f"- **Tests-failed delta:** {delta if delta is not None else '-'}")
    lines.append(f"- **Summary:** {cmp_dict.get('summary', '')}")
    for label, key in (
        ("New failure classes", "new_failure_classes"),
        ("Resolved failure classes", "resolved_failure_classes"),
        ("Unchanged failure classes", "unchanged_failure_classes"),
    ):
        values = cmp_dict.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.append("")
            for value in values:
                lines.append(f"- {value}")
    return "\n".join(lines) + "\n"
