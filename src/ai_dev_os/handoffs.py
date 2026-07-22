"""Role-specific manual handoff packet generation."""

from __future__ import annotations

from pathlib import Path

from .adapters.base import AUTOMATION_STATUS, AdapterResult
from .context_builder import build_context_packet, write_context_packet
from .fingerprints import fingerprint_context_manifest, fingerprint_plan
from .git_safety import inspect_repo
from .lifecycle_gates import assert_can_prepare_implementation_handoff
from .models import ModelRole, Plan, Task, utc_now_iso
from .report_store import ReportStore
from .routing import get_budget_limits, select_token_budget_band
from .validation import ValidationError


def prepare_role_handoff(
    role: ModelRole,
    task: Task,
    project_root: str | Path,
    output_dir: str | Path,
    *,
    plan: Plan | None = None,
    project_rules: list[str] | None = None,
    require_clean_worktree: bool = True,
) -> AdapterResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(project_root)

    if role is ModelRole.CURSOR:
        assert_can_prepare_implementation_handoff(
            task, plan, root, require_clean_worktree=require_clean_worktree
        )
        body = _cursor_impl_handoff(task, plan)  # type: ignore[arg-type]
    elif role is ModelRole.CLAUDE:
        body = _claude_planning_handoff(task, root, project_rules or [])
    elif role is ModelRole.CODEX:
        if plan is None or plan.status.value != "approved":
            # Review can proceed with latest approved plan preferred.
            raise ValidationError(
                "Codex review handoff requires an approved plan"
            )
        body = _codex_review_handoff(task, plan, root)
    else:
        raise ValidationError(f"Unsupported handoff role: {role}")

    # Always include a minimal context packet alongside role handoff.
    packet = build_context_packet(task, root)
    packet.manifest["content_fingerprint"] = fingerprint_context_manifest(packet.manifest)
    write_context_packet(packet, out, task.id)

    handoff_path = out / f"{task.id}.{role.value}.handoff.md"
    handoff_path.write_text(body, encoding="utf-8")
    return AdapterResult(
        role=role,
        handoff_path=handoff_path,
        automation_status=AUTOMATION_STATUS,
        message=(
            f"{role.value} handoff ready at {handoff_path}. "
            "Manual paste required; no API call was made."
        ),
    )


def _claude_planning_handoff(task: Task, root: Path, project_rules: list[str]) -> str:
    band = task.token_budget_band or select_token_budget_band(task)
    budget = get_budget_limits(band)
    lines = [
        "# Claude Planning Handoff",
        "",
        f"- Generated: {utc_now_iso()}",
        f"- automation_status: {AUTOMATION_STATUS}",
        f"- Task: {task.id}",
        f"- Project root: `{root}`",
        "",
        "## Objective",
        task.description,
        "",
        "## Acceptance Criteria",
    ]
    lines.extend(f"- {c}" for c in (task.acceptance_criteria or ["(none)"]))
    lines.extend(["", "## Minimum Context", f"- Title: {task.title}", f"- Type: {task.task_type.value}", f"- Risk: {task.risk_level.value}"])
    lines.extend(["", "## Project Rules"])
    if project_rules:
        lines.extend(f"- {r}" for r in project_rules)
    else:
        lines.append("- Stay within registered project root; no Equitify access.")
        lines.append("- Manual handoff only; no paid LLM APIs from ai-dev-os.")
    lines.extend(
        [
            "",
            "## Risks",
            f"- Task risk level: {task.risk_level.value}",
            "",
            "## Token Budget",
            f"- Band: {budget['band']}",
            f"- Max input: {budget['max_input_tokens']}",
            f"- Max output: {budget['max_output_tokens']}",
            "",
            "## Instructions",
            "1. Open Claude manually.",
            "2. Produce a plan artifact covering objective, scope, steps, tests, rollback, risks.",
            "3. Return the plan for `ai-dev-os create-plan` / approval — do not implement yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _cursor_impl_handoff(task: Task, plan: Plan) -> str:
    fp = plan.approved_fingerprint or fingerprint_plan(plan.to_dict())
    lines = [
        "# Cursor Implementation Handoff",
        "",
        f"- Generated: {utc_now_iso()}",
        f"- automation_status: {AUTOMATION_STATUS}",
        f"- Task: {task.id}",
        f"- Plan: {plan.plan_id}",
        f"- Plan fingerprint: `{fp}`",
        f"- Starting commit: `{plan.starting_commit}`",
        "",
        "## Approved Plan Only",
        f"**Objective:** {plan.objective}",
        "",
        "### Scope",
    ]
    lines.extend(f"- {s}" for s in plan.scope or ["(see objective)"])
    lines.extend(["", "### Exact Allowed Scope / Expected Files"])
    lines.extend(f"- `{p}`" for p in plan.files_expected_to_change)
    lines.extend(["", "### Prohibited Actions"])
    lines.extend(f"- {p}" for p in (plan.prohibited_actions or ["(none listed)"]))
    lines.extend(["", "### Implementation Steps"])
    for i, step in enumerate(plan.implementation_steps, 1):
        lines.append(f"{i}. {step}")
    lines.extend(["", "### Required Tests"])
    lines.extend(f"- {t}" for t in plan.testing_plan)
    lines.extend(
        [
            "",
            "## Report Format",
            "After manual implementation, record with:",
            "`ai-dev-os record-report --kind implementation --task-id "
            f"{task.id} --summary '...' --outcome success "
            "--file-changed <path> --test-run <cmd>`",
            "",
            "## Safety",
            "- Do not change scope without reapproval.",
            "- Do not call paid APIs from ai-dev-os.",
            "- Stay on starting commit baseline unless plan says otherwise.",
            "",
        ]
    )
    return "\n".join(lines)


def _codex_review_handoff(task: Task, plan: Plan, root: Path) -> str:
    store = ReportStore()
    impls = store.list_implementation(task.id)
    latest_impl = impls[-1] if impls else None
    try:
        inspection = inspect_repo(root)
        diff_summary = (
            f"branch={inspection.branch} head={inspection.head} dirty={inspection.dirty}"
        )
        if inspection.status_porcelain.strip():
            diff_summary += "\n```\n" + inspection.status_porcelain.strip() + "\n```"
    except Exception as exc:  # inspect-only
        diff_summary = f"(git inspect unavailable: {exc})"

    lines = [
        "# Codex Review Handoff",
        "",
        f"- Generated: {utc_now_iso()}",
        f"- automation_status: {AUTOMATION_STATUS}",
        f"- Task: {task.id}",
        f"- Plan: {plan.plan_id} (fingerprint `{plan.approved_fingerprint}`)",
        "",
        "## Approved Plan",
        f"- Objective: {plan.objective}",
        f"- Starting commit: `{plan.starting_commit}`",
        "",
        "## Implementation Report",
    ]
    if latest_impl:
        lines.extend(
            [
                f"- Summary: {latest_impl.summary}",
                f"- Outcome: {latest_impl.outcome.value}",
                f"- Files: {', '.join(latest_impl.files_changed) or '(none)'}",
                f"- Tests: {', '.join(latest_impl.tests_run) or '(none)'}",
                f"- Fingerprint: `{latest_impl.content_fingerprint}`",
            ]
        )
    else:
        lines.append("- (no implementation report recorded yet)")
    lines.extend(["", "## Git Diff Summary / Status", diff_summary])
    lines.extend(["", "## Acceptance Criteria"])
    lines.extend(f"- {c}" for c in (task.acceptance_criteria or ["(none)"]))
    lines.extend(["", "## Required Tests"])
    lines.extend(f"- {t}" for t in plan.testing_plan)
    lines.extend(
        [
            "",
            "## Safety Checklist",
            "- [ ] Scope matches approved plan",
            "- [ ] No prohibited paths touched",
            "- [ ] Starting commit / fingerprint gates respected",
            "- [ ] No secrets introduced",
            "- [ ] Tests listed were run",
            "",
            "## Explicit Request",
            "Return **confirmed findings** and **rejected findings** separately.",
            "Do not silently edit the implementation report.",
            "Verdict must be one of: pass | pass_with_notes | changes_required | blocked.",
            "",
            "Record with:",
            f"`ai-dev-os record-report --kind review --task-id {task.id} "
            "--reviewer-role codex --verdict pass "
            "--confirmed-finding 'severity|summary' "
            "--rejected-finding 'severity|summary'`",
            "",
        ]
    )
    return "\n".join(lines)
