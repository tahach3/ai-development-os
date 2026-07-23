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
