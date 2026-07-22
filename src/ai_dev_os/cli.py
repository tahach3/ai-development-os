"""CLI for AI Development Operating System."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .approval import approve_plan, reject_plan, submit_plan, apply_plan_content_update
from .behavioral_metrics import (
    generate_behavioral_report,
    render_behavioral_markdown,
    write_behavioral_report,
)
from .context_builder import build_context_packet, write_context_packet
from .fingerprints import (
    fingerprint_implementation_report,
    fingerprint_plan,
    fingerprint_task,
)
from .execution_audit import ExecutionAuditStore
from .git_safety import inspect_repo
from .handoffs import prepare_role_handoff
from .lifecycle_gates import (
    GateError,
    assert_can_create_plan,
    assert_project_rules_compatible,
    next_allowed_action,
)
from .models import (
    FindingSeverity,
    ImplementationReport,
    ModelRole,
    PlanStatus,
    ProjectRecord,
    RepairRound,
    ReportOutcome,
    ReviewFinding,
    ReviewReport,
    ReviewVerdict,
    RiskLevel,
    TaskStatus,
    TokenUsage,
    TokenUsageMode,
)
from .plan_store import PlanStore
from .project_registry import ProjectRegistry, ProjectRegistryError, example_registry_path
from .repair_rounds import RepairRoundStore, load_max_repair_rounds
from .report_store import ReportStore
from .review_gate import apply_review_verdict
from .routing import apply_routing, route_task
from .session_exec import run_session_tests
from .session_store import SessionError, SessionStore
from .task_store import TaskStore
from .validation import (
    ValidationError,
    apply_status_transition,
    validate_plan_dict,
    validate_task_dict,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_finding(raw: str) -> ReviewFinding:
    parts = raw.split("|", 2)
    if len(parts) < 2:
        raise ValidationError(
            "Finding format must be severity|summary or severity|summary|path"
        )
    return ReviewFinding(
        severity=FindingSeverity(parts[0]),
        summary=parts[1],
        path=parts[2] if len(parts) > 2 else None,
    )


def cmd_init(_args: argparse.Namespace) -> int:
    root = _repo_root()
    for rel in (
        "workspace/active",
        "workspace/completed",
        "workspace/decisions",
        "workspace/behavioral_reports",
        "workspace/reports/implementation",
        "workspace/reports/review",
        "workspace/handoffs",
        "workspace/context",
        "workspace/plans",
        "workspace/repair_rounds",
        "workspace/sessions",
        "workspace/executions",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    registry_path = root / "config" / "projects.yaml"
    if not registry_path.exists():
        example = example_registry_path()
        registry_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Initialized workspace under {root}")
    print(f"Project registry: {registry_path} (Equitify not registered)")
    return 0


def cmd_register_project(args: argparse.Namespace) -> int:
    registry = ProjectRegistry()
    record = ProjectRecord(
        id=args.id,
        name=args.name,
        root_path=args.root,
        description=args.description or "",
        default_branch=args.default_branch,
        allowed_path_prefixes=list(args.allowed_prefix or []),
        prohibited_path_prefixes=list(args.prohibited_prefix or []),
        active=True,
    )
    try:
        registry.register(record, overwrite=bool(args.overwrite))
    except ProjectRegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Registered project '{record.id}' at {record.root_path}")
    return 0


def cmd_create_task(args: argparse.Namespace) -> int:
    registry = ProjectRegistry()
    try:
        registry.require(args.project_id)
    except ProjectRegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.from_file:
        with Path(args.from_file).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    else:
        data = {
            "id": args.id,
            "title": args.title,
            "description": args.description,
            "project_id": args.project_id,
            "task_type": args.task_type,
            "complexity": args.complexity,
            "risk_level": args.risk_level,
            "status": TaskStatus.DRAFT.value,
            "acceptance_criteria": list(args.acceptance or []),
            "allowed_paths": list(args.allowed_path or []),
            "prohibited_paths": list(args.prohibited_path or []),
        }
    data["project_id"] = data.get("project_id") or args.project_id
    store = TaskStore()
    try:
        task = store.create(data)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Created task {task.id} (status={task.status.value})")
    return 0


def cmd_set_task_status(args: argparse.Namespace) -> int:
    store = TaskStore()
    try:
        task = store.load(args.task_id)
        new_status = TaskStatus(args.status)
        updated = apply_status_transition(task, new_status)
        if args.blocked_reason:
            updated.blocked_reason = args.blocked_reason
        store.update(updated)
    except (ValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Task {updated.id} → {updated.status.value}")
    return 0


def cmd_validate_task(args: argparse.Namespace) -> int:
    store = TaskStore()
    registry = ProjectRegistry()
    try:
        if args.file:
            with Path(args.file).open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            task = validate_task_dict(data)
        else:
            task = store.load(args.task_id)
        registry.require(task.project_id)
        for path in list(task.allowed_paths) + list(task.prohibited_paths):
            registry.ensure_path_allowed(task.project_id, path)
    except (ValidationError, ProjectRegistryError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"VALID: task {task.id} for project {task.project_id}")
    return 0


def cmd_route_task(args: argparse.Namespace) -> int:
    store = TaskStore()
    try:
        task = store.load(args.task_id)
        decision = route_task(task)
        updated = apply_routing(task, decision)
        store.update(updated)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Routed {updated.id} → {decision.role.value}")
    print(f"Budget band: {decision.token_budget_band.value}")
    print(f"Explanation: {decision.explanation}")
    return 0


def cmd_build_context(args: argparse.Namespace) -> int:
    store = TaskStore()
    registry = ProjectRegistry()
    try:
        task = store.load(args.task_id)
        root = registry.resolve_root(task.project_id)
    except (ValidationError, ProjectRegistryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out_dir = Path(args.output) if args.output else (_repo_root() / "workspace" / "context")
    packet = build_context_packet(task, root)
    write_context_packet(packet, out_dir, task.id)
    print(f"Wrote {packet.markdown_path}")
    print(f"Wrote {packet.manifest_path}")
    return 0


def cmd_prepare_handoff(args: argparse.Namespace) -> int:
    store = TaskStore()
    registry = ProjectRegistry()
    plan_store = PlanStore()
    try:
        task = store.load(args.task_id)
        if not task.assigned_role:
            task = apply_routing(task)
            store.update(task)
        root = registry.resolve_root(task.project_id)
        role_name = args.role or (task.assigned_role.value if task.assigned_role else None)
        if not role_name:
            raise ValidationError("No role specified and task is unassigned")
        role = ModelRole(role_name)
        plan = plan_store.approved_for_task(task.id) or plan_store.latest_for_task(task.id)
        out_dir = Path(args.output) if args.output else (_repo_root() / "workspace" / "handoffs")
        result = prepare_role_handoff(
            role,
            task,
            root,
            out_dir,
            plan=plan,
            require_clean_worktree=not bool(args.allow_dirty),
        )
    except (ValidationError, ProjectRegistryError, GateError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(result.message)
    print(f"automation_status: {result.automation_status}")
    return 0


def cmd_create_plan(args: argparse.Namespace) -> int:
    task_store = TaskStore()
    plan_store = PlanStore()
    registry = ProjectRegistry()
    try:
        task = task_store.load(args.task_id)
        assert_can_create_plan(task)
        assert_project_rules_compatible(registry, task)
        root = registry.resolve_root(task.project_id)
        inspection = inspect_repo(root)
        if not inspection.head:
            raise ValidationError("Cannot create plan without git HEAD")
        starting = args.starting_commit or inspection.head

        if args.from_file:
            with Path(args.from_file).open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        else:
            data = {
                "plan_id": args.plan_id,
                "task_id": task.id,
                "project_id": task.project_id,
                "planner_agent": args.planner_agent,
                "starting_commit": starting,
                "objective": args.objective,
                "assumptions": list(args.assumption or []),
                "scope": list(args.scope or []),
                "prohibited_actions": list(args.prohibited_action or []),
                "files_expected_to_change": list(args.file_expected or []),
                "implementation_steps": list(args.step or []),
                "testing_plan": list(args.test or []),
                "rollback_or_recovery_plan": list(args.rollback or []),
                "risks": list(args.risk or []),
                "unresolved_questions": list(args.question or []),
                "approval_requirement": args.approval_requirement,
                "risk_level": args.risk_level or task.risk_level.value,
            }
        data["task_id"] = task.id
        data["project_id"] = task.project_id
        data.setdefault("starting_commit", starting)
        data.setdefault("plan_id", args.plan_id)
        data.setdefault("planner_agent", args.planner_agent)
        plan = plan_store.create(data)
        print(f"Created plan {plan.plan_id} (status={plan.status.value})")
        print(f"content_fingerprint: {plan.content_fingerprint}")
    except (ValidationError, ProjectRegistryError, GateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_validate_plan(args: argparse.Namespace) -> int:
    plan_store = PlanStore()
    try:
        if args.file:
            with Path(args.file).open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            plan = validate_plan_dict(data)
        else:
            plan = plan_store.load(args.plan_id)
        fp = fingerprint_plan(plan.to_dict())
    except ValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"VALID: plan {plan.plan_id} fingerprint={fp}")
    return 0


def cmd_submit_plan(args: argparse.Namespace) -> int:
    plan_store = PlanStore()
    task_store = TaskStore()
    try:
        plan = submit_plan(plan_store, args.plan_id)
        task = task_store.load(plan.task_id)
        if task.status is TaskStatus.READY_FOR_PLANNING:
            task = apply_status_transition(task, TaskStatus.PLANNED)
            meta = dict(task.metadata)
            meta["current_plan_id"] = plan.plan_id
            task.metadata = meta
            task_store.update(task)
        print(f"Submitted plan {plan.plan_id} → {plan.status.value}")
        print(f"Task {task.id} status={task.status.value}")
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_approve_plan(args: argparse.Namespace) -> int:
    try:
        plan = approve_plan(
            PlanStore(),
            TaskStore(),
            args.plan_id,
            approver=args.approver,
            note=args.note,
        )
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Approved plan {plan.plan_id} by {plan.approved_by}")
    print(f"approved_fingerprint: {plan.approved_fingerprint}")
    print(f"approved_timestamp: {plan.approved_timestamp}")
    return 0


def cmd_reject_plan(args: argparse.Namespace) -> int:
    try:
        plan = reject_plan(
            PlanStore(),
            args.plan_id,
            rejected_by=args.rejected_by,
            reason=args.reason,
        )
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Rejected plan {plan.plan_id}: {plan.rejection_reason}")
    return 0


def cmd_show_plan(args: argparse.Namespace) -> int:
    plan_store = PlanStore()
    try:
        plan = plan_store.load(args.plan_id)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        print(f"Plan: {plan.plan_id}")
        print(f"  task_id: {plan.task_id}")
        print(f"  status: {plan.status.value}")
        print(f"  planner_agent: {plan.planner_agent}")
        print(f"  starting_commit: {plan.starting_commit}")
        print(f"  objective: {plan.objective}")
        print(f"  content_fingerprint: {plan.content_fingerprint}")
        print(f"  approved_fingerprint: {plan.approved_fingerprint}")
        print(f"  approved_by: {plan.approved_by}")
        print(f"  approved_timestamp: {plan.approved_timestamp}")
        print(f"  approval_note: {plan.approval_note}")
    return 0


def cmd_update_plan(args: argparse.Namespace) -> int:
    """Update plan fields from file; invalidates approval if content changes."""
    plan_store = PlanStore()
    try:
        with Path(args.file).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        data["plan_id"] = args.plan_id
        plan = validate_plan_dict(data)
        updated = apply_plan_content_update(plan_store, plan)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Updated plan {updated.plan_id} status={updated.status.value}")
    print(f"content_fingerprint: {updated.content_fingerprint}")
    return 0


def cmd_record_report(args: argparse.Namespace) -> int:
    store = ReportStore()
    task_store = TaskStore()
    plan_store = PlanStore()
    try:
        task = task_store.load(args.task_id)
        if args.kind == "implementation":
            plan = plan_store.approved_for_task(task.id)
            usage = TokenUsage(
                mode=TokenUsageMode(args.usage_mode),
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
                notes=args.usage_notes,
            )
            if usage.mode is TokenUsageMode.UNAVAILABLE:
                usage.input_tokens = None
                usage.output_tokens = None
            report = ImplementationReport(
                task_id=args.task_id,
                summary=args.summary,
                files_changed=list(args.file_changed or []),
                tests_run=list(args.test_run or []),
                outcome=ReportOutcome(args.outcome),
                token_usage=usage,
                notes=args.notes,
                plan_fingerprint=(
                    plan.approved_fingerprint if plan else None
                ),
                task_fingerprint=fingerprint_task(task.to_dict()),
            )
            report.content_fingerprint = fingerprint_implementation_report(
                report.to_dict()
            )
            path = store.save_implementation(report)
            if task.status is TaskStatus.APPROVED_FOR_IMPLEMENTATION:
                task = apply_status_transition(task, TaskStatus.IMPLEMENTING)
            if task.status is TaskStatus.IMPLEMENTING:
                task = apply_status_transition(task, TaskStatus.VALIDATING)
            if args.outcome == ReportOutcome.SUCCESS.value and task.status is TaskStatus.VALIDATING:
                task = apply_status_transition(task, TaskStatus.READY_FOR_REVIEW)
            task_store.update(task)
        else:
            confirmed = [_parse_finding(r) for r in (args.confirmed_finding or [])]
            rejected = [_parse_finding(r) for r in (args.rejected_finding or [])]
            findings = [_parse_finding(r) for r in (args.finding or [])]
            if not findings and confirmed:
                findings = list(confirmed)
            impl = store.latest_implementation(args.task_id)
            report = ReviewReport(
                task_id=args.task_id,
                reviewer_role=ModelRole(args.reviewer_role),
                verdict=ReviewVerdict(args.verdict),
                findings=findings,
                confirmed_findings=confirmed,
                rejected_findings=rejected,
                notes=args.notes,
                implementation_report_fingerprint=(
                    impl.content_fingerprint if impl else None
                ),
            )
            path = store.save_review(report)
            if task.status is TaskStatus.READY_FOR_REVIEW:
                task = apply_review_verdict(task, report)
                task_store.update(task)
    except (ValidationError, ValueError, GateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Recorded {args.kind} report at {path}")
    return 0


def cmd_record_repair_round(args: argparse.Namespace) -> int:
    store = RepairRoundStore()
    task_store = TaskStore()
    try:
        rnd = RepairRound(
            task_id=args.task_id,
            round_number=int(args.round_number or 0),
            reason=args.reason,
            findings_addressed=list(args.finding_addressed or []),
            files_changed=list(args.file_changed or []),
            tests_rerun=list(args.test_rerun or []),
            result=args.result,
            scope_changed=bool(args.scope_changed),
            reapproval_required=bool(args.reapproval_required),
        )
        recorded, task = store.record(
            rnd,
            task_store=task_store,
            max_rounds=load_max_repair_rounds(),
        )
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Recorded repair round {recorded.round_number} for {recorded.task_id}; "
        f"task_status={task.status.value}"
    )
    return 0


def cmd_review_status(args: argparse.Namespace) -> int:
    store = ReportStore()
    task_store = TaskStore()
    try:
        task = task_store.load(args.task_id)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    latest = store.latest_review(args.task_id)
    print(f"Task: {task.id} status={task.status.value}")
    if not latest:
        print("Review: none recorded")
        return 0
    print(f"Latest review verdict: {latest.verdict.value} by {latest.reviewer_role.value}")
    print(f"Findings: {len(latest.findings)}")
    print(f"Confirmed: {len(latest.confirmed_findings)}")
    print(f"Rejected: {len(latest.rejected_findings)}")
    for finding in latest.confirmed_findings or latest.findings:
        loc = f" ({finding.path})" if finding.path else ""
        print(f"  - [{finding.severity.value}] {finding.summary}{loc}")
    return 0


def cmd_behavioral_report(args: argparse.Namespace) -> int:
    tasks = TaskStore().list_tasks(include_completed=True)
    report = generate_behavioral_report(tasks)
    path = write_behavioral_report(report)
    md = render_behavioral_markdown(report)
    md_path = path.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(md)
    print(f"Wrote {path}")
    print(f"Wrote {md_path}")
    return 0


def cmd_project_status(args: argparse.Namespace) -> int:
    registry = ProjectRegistry()
    plan_store = PlanStore()
    report_store = ReportStore()
    repair_store = RepairRoundStore()
    try:
        if args.project_id:
            projects = [registry.require(args.project_id)]
        else:
            projects = registry.list_projects()
    except ProjectRegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    tasks = TaskStore().list_tasks(include_completed=True)
    if not projects:
        print("No projects registered.")
        return 0
    for project in projects:
        print(f"Project: {project.id} ({project.name})")
        print(f"  root: {project.root_path}")
        print(f"  active: {project.active}")
        related = [t for t in tasks if t.project_id == project.id]
        active = [t for t in related if t.status is not TaskStatus.COMPLETED]
        print(f"  tasks: {len(related)} (active={len(active)})")
        for t in active:
            plan = plan_store.latest_for_task(t.id)
            review = report_store.latest_review(t.id)
            repair_count = repair_store.count(t.id)
            approval = "n/a"
            plan_state = "none"
            if plan:
                plan_state = plan.status.value
                if plan.status is PlanStatus.APPROVED:
                    approval = f"approved_by={plan.approved_by}"
                elif plan.status is PlanStatus.READY_FOR_APPROVAL:
                    approval = "pending"
                elif plan.status is PlanStatus.REJECTED:
                    approval = "rejected"
                else:
                    approval = plan.status.value
            blockers = []
            if t.status is TaskStatus.BLOCKED:
                blockers.append(t.blocked_reason or "blocked")
            if t.status is TaskStatus.CANCELLED:
                blockers.append("cancelled")
            print(f"  - task {t.id}")
            print(f"      task_state: {t.status.value}")
            print(f"      plan_state: {plan_state}")
            print(f"      approval_status: {approval}")
            print(
                f"      assigned_agent: "
                f"{t.assigned_role.value if t.assigned_role else 'unassigned'}"
            )
            print(
                f"      review_verdict: "
                f"{review.verdict.value if review else 'none'}"
            )
            print(f"      repair_round_count: {repair_count}")
            print(f"      blockers: {', '.join(blockers) if blockers else 'none'}")
            print(f"      next_allowed_action: {next_allowed_action(t, plan)}")
        try:
            inspection = inspect_repo(project.root_path)
            print(
                f"  git: repo={inspection.is_repo} branch={inspection.branch} "
                f"dirty={inspection.dirty}"
            )
        except Exception as exc:  # inspect-only; never mutate
            print(f"  git: inspect failed ({exc})")
    return 0


def cmd_create_session(args: argparse.Namespace) -> int:
    store = SessionStore()
    try:
        record = store.create(
            project_id=args.project_id,
            task_id=args.task_id,
            session_id=args.session_id,
        )
    except (SessionError, ProjectRegistryError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Created session {record.session_id}")
    print(f"  project_id: {record.project_id}")
    print(f"  starting_commit: {record.starting_commit}")
    print(f"  worktree_path: {record.worktree_path}")
    print(f"  status: {record.status.value}")
    return 0


def cmd_show_session(args: argparse.Namespace) -> int:
    store = SessionStore()
    try:
        record = store.load(args.session_id)
    except SessionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"Session: {record.session_id}")
        print(f"  project_id: {record.project_id}")
        print(f"  task_id: {record.task_id}")
        print(f"  status: {record.status.value}")
        print(f"  starting_commit: {record.starting_commit}")
        print(f"  worktree_path: {record.worktree_path}")
        print(f"  project_root: {record.project_root}")
    return 0


def cmd_list_sessions(_args: argparse.Namespace) -> int:
    store = SessionStore()
    sessions = store.list_sessions()
    if not sessions:
        print("No sessions.")
        return 0
    for record in sessions:
        print(
            f"{record.session_id}  project={record.project_id}  "
            f"status={record.status.value}  commit={record.starting_commit[:12]}"
        )
    return 0


def cmd_cleanup_session(args: argparse.Namespace) -> int:
    store = SessionStore()
    try:
        record = store.cleanup(args.session_id)
    except SessionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Cleaned session {record.session_id} status={record.status.value}")
    print(f"  worktree_path: {record.worktree_path}")
    return 0


def cmd_run_tests(args: argparse.Namespace) -> int:
    try:
        envelope = run_session_tests(
            args.session_id,
            test_paths=list(args.test_path or []) or None,
            timeout=args.timeout,
            output_limit_bytes=args.output_limit,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"execution_id: {envelope.execution_id}")
    print(f"policy_decision: {envelope.policy_decision.value}")
    print(f"execution_status: {envelope.execution_status.value}")
    print(f"exit_code: {envelope.exit_code}")
    print(f"timeout_status: {envelope.timeout_status}")
    print(f"automation_status: {envelope.automation_status}")
    if envelope.rejection_reason:
        print(f"rejection_reason: {envelope.rejection_reason}")
    if args.json:
        print(json.dumps(envelope.to_dict(), indent=2, sort_keys=True))
    return 0 if envelope.policy_decision.value == "allow" and envelope.execution_status.value == "success" else 1


def cmd_show_execution(args: argparse.Namespace) -> int:
    store = ExecutionAuditStore()
    try:
        envelope = store.load(args.execution_id)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(envelope.to_dict(), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-dev-os",
        description="AI Development Operating System (Round 3A)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize local workspace directories and registry")
    p_init.set_defaults(func=cmd_init)

    p_reg = sub.add_parser("register-project", help="Register a project (not Equitify)")
    p_reg.add_argument("--id", required=True)
    p_reg.add_argument("--name", required=True)
    p_reg.add_argument("--root", required=True, help="Absolute or relative project root path")
    p_reg.add_argument("--description", default="")
    p_reg.add_argument("--default-branch", default="main")
    p_reg.add_argument("--allowed-prefix", action="append", default=[])
    p_reg.add_argument("--prohibited-prefix", action="append", default=[])
    p_reg.add_argument("--overwrite", action="store_true")
    p_reg.set_defaults(func=cmd_register_project)

    p_create = sub.add_parser("create-task", help="Create a draft task for a registered project")
    p_create.add_argument("--project-id", required=True)
    p_create.add_argument("--from-file", help="YAML task file")
    p_create.add_argument("--id")
    p_create.add_argument("--title")
    p_create.add_argument("--description")
    p_create.add_argument("--task-type", default="feature")
    p_create.add_argument("--complexity", default="normal")
    p_create.add_argument("--risk-level", default="medium")
    p_create.add_argument("--acceptance", action="append", default=[])
    p_create.add_argument("--allowed-path", action="append", default=[])
    p_create.add_argument("--prohibited-path", action="append", default=[])
    p_create.set_defaults(func=cmd_create_task)

    p_sts = sub.add_parser("set-task-status", help="Transition task lifecycle status")
    p_sts.add_argument("--task-id", required=True)
    p_sts.add_argument("--status", required=True, choices=[s.value for s in TaskStatus])
    p_sts.add_argument("--blocked-reason", default=None)
    p_sts.set_defaults(func=cmd_set_task_status)

    p_val = sub.add_parser("validate-task", help="Validate a task file or stored task")
    p_val.add_argument("--task-id")
    p_val.add_argument("--file")
    p_val.set_defaults(func=cmd_validate_task)

    p_route = sub.add_parser("route-task", help="Deterministically route a task")
    p_route.add_argument("--task-id", required=True)
    p_route.set_defaults(func=cmd_route_task)

    p_ctx = sub.add_parser("build-context", help="Build minimal context packet")
    p_ctx.add_argument("--task-id", required=True)
    p_ctx.add_argument("--output")
    p_ctx.set_defaults(func=cmd_build_context)

    p_hand = sub.add_parser("prepare-handoff", help="Prepare role-specific manual handoff")
    p_hand.add_argument("--task-id", required=True)
    p_hand.add_argument("--role", choices=["claude", "cursor", "codex"])
    p_hand.add_argument("--output")
    p_hand.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Skip clean-worktree check (tests/debug only)",
    )
    p_hand.set_defaults(func=cmd_prepare_handoff)

    p_cp = sub.add_parser("create-plan", help="Create a draft plan for a ready task")
    p_cp.add_argument("--task-id", required=True)
    p_cp.add_argument("--plan-id", required=True)
    p_cp.add_argument("--planner-agent", required=True)
    p_cp.add_argument("--objective")
    p_cp.add_argument("--starting-commit")
    p_cp.add_argument("--from-file")
    p_cp.add_argument("--assumption", action="append", default=[])
    p_cp.add_argument("--scope", action="append", default=[])
    p_cp.add_argument("--prohibited-action", action="append", default=[])
    p_cp.add_argument("--file-expected", action="append", default=[])
    p_cp.add_argument("--step", action="append", default=[])
    p_cp.add_argument("--test", action="append", default=[])
    p_cp.add_argument("--rollback", action="append", default=[])
    p_cp.add_argument("--risk", action="append", default=[])
    p_cp.add_argument("--question", action="append", default=[])
    p_cp.add_argument("--approval-requirement", default="human")
    p_cp.add_argument("--risk-level", choices=[r.value for r in RiskLevel])
    p_cp.set_defaults(func=cmd_create_plan)

    p_vp = sub.add_parser("validate-plan", help="Validate a plan file or stored plan")
    p_vp.add_argument("--plan-id")
    p_vp.add_argument("--file")
    p_vp.set_defaults(func=cmd_validate_plan)

    p_sp = sub.add_parser("submit-plan", help="Submit plan for approval")
    p_sp.add_argument("--plan-id", required=True)
    p_sp.set_defaults(func=cmd_submit_plan)

    p_ap = sub.add_parser("approve-plan", help="Approve a submitted plan")
    p_ap.add_argument("--plan-id", required=True)
    p_ap.add_argument("--approver", required=True)
    p_ap.add_argument("--note", default=None)
    p_ap.set_defaults(func=cmd_approve_plan)

    p_rp = sub.add_parser("reject-plan", help="Reject a plan")
    p_rp.add_argument("--plan-id", required=True)
    p_rp.add_argument("--rejected-by", required=True)
    p_rp.add_argument("--reason", required=True)
    p_rp.set_defaults(func=cmd_reject_plan)

    p_shp = sub.add_parser("show-plan", help="Show plan details")
    p_shp.add_argument("--plan-id", required=True)
    p_shp.add_argument("--json", action="store_true")
    p_shp.set_defaults(func=cmd_show_plan)

    p_up = sub.add_parser("update-plan", help="Update plan from YAML (may invalidate approval)")
    p_up.add_argument("--plan-id", required=True)
    p_up.add_argument("--file", required=True)
    p_up.set_defaults(func=cmd_update_plan)

    p_rep = sub.add_parser("record-report", help="Record implementation or review report")
    p_rep.add_argument("--kind", required=True, choices=["implementation", "review"])
    p_rep.add_argument("--task-id", required=True)
    p_rep.add_argument("--summary", default="")
    p_rep.add_argument("--outcome", choices=[o.value for o in ReportOutcome])
    p_rep.add_argument("--file-changed", action="append", default=[])
    p_rep.add_argument("--test-run", action="append", default=[])
    p_rep.add_argument("--usage-mode", default="unavailable", choices=[m.value for m in TokenUsageMode])
    p_rep.add_argument("--input-tokens", type=int, default=None)
    p_rep.add_argument("--output-tokens", type=int, default=None)
    p_rep.add_argument("--usage-notes", default=None)
    p_rep.add_argument("--reviewer-role", choices=[m.value for m in ModelRole])
    p_rep.add_argument("--verdict", choices=[v.value for v in ReviewVerdict])
    p_rep.add_argument("--finding", action="append", default=[])
    p_rep.add_argument("--confirmed-finding", action="append", default=[])
    p_rep.add_argument("--rejected-finding", action="append", default=[])
    p_rep.add_argument("--notes", default=None)
    p_rep.set_defaults(func=cmd_record_report)

    p_rr = sub.add_parser("record-repair-round", help="Record a repair round")
    p_rr.add_argument("--task-id", required=True)
    p_rr.add_argument("--round-number", type=int, default=0)
    p_rr.add_argument("--reason", required=True)
    p_rr.add_argument("--finding-addressed", action="append", default=[])
    p_rr.add_argument("--file-changed", action="append", default=[])
    p_rr.add_argument("--test-rerun", action="append", default=[])
    p_rr.add_argument("--result", default="pending")
    p_rr.add_argument("--scope-changed", action="store_true")
    p_rr.add_argument("--reapproval-required", action="store_true")
    p_rr.set_defaults(func=cmd_record_repair_round)

    p_rev = sub.add_parser("review-status", help="Show latest review status for a task")
    p_rev.add_argument("--task-id", required=True)
    p_rev.set_defaults(func=cmd_review_status)

    p_beh = sub.add_parser("behavioral-report", help="Generate behavioral metrics report")
    p_beh.add_argument("--json", action="store_true")
    p_beh.set_defaults(func=cmd_behavioral_report)

    p_ps = sub.add_parser("project-status", help="Show project and task status")
    p_ps.add_argument("--project-id")
    p_ps.set_defaults(func=cmd_project_status)

    p_cs = sub.add_parser(
        "create-session",
        help="Create isolated worktree session for a registered project",
    )
    p_cs.add_argument("--project-id", required=True)
    p_cs.add_argument("--task-id", default=None)
    p_cs.add_argument("--session-id", default=None)
    p_cs.set_defaults(func=cmd_create_session)

    p_ss = sub.add_parser("show-session", help="Show session record")
    p_ss.add_argument("--session-id", required=True)
    p_ss.add_argument("--json", action="store_true")
    p_ss.set_defaults(func=cmd_show_session)

    p_ls = sub.add_parser("list-sessions", help="List isolated sessions")
    p_ls.set_defaults(func=cmd_list_sessions)

    p_cl = sub.add_parser("cleanup-session", help="Remove session worktree safely")
    p_cl.add_argument("--session-id", required=True)
    p_cl.set_defaults(func=cmd_cleanup_session)

    p_rt = sub.add_parser(
        "run-tests",
        help="Run allowlisted targeted pytest inside a session worktree",
    )
    p_rt.add_argument("--session-id", required=True)
    p_rt.add_argument(
        "--test-path",
        action="append",
        default=[],
        help="Relative test path under the session worktree (repeatable)",
    )
    p_rt.add_argument("--timeout", type=float, default=None)
    p_rt.add_argument("--output-limit", type=int, default=None)
    p_rt.add_argument("--json", action="store_true")
    p_rt.set_defaults(func=cmd_run_tests)

    p_se = sub.add_parser("show-execution", help="Show persisted execution envelope")
    p_se.add_argument("--execution-id", required=True)
    p_se.set_defaults(func=cmd_show_execution)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "create-task" and not args.from_file:
        missing = [n for n in ("id", "title", "description") if not getattr(args, n)]
        if missing:
            parser.error(f"create-task requires --from-file or {', '.join('--' + m for m in missing)}")
    if args.command == "validate-task" and not args.task_id and not args.file:
        parser.error("validate-task requires --task-id or --file")
    if args.command == "validate-plan" and not args.plan_id and not args.file:
        parser.error("validate-plan requires --plan-id or --file")
    if args.command == "create-plan" and not args.from_file:
        missing = []
        if not args.objective:
            missing.append("--objective")
        if not args.step:
            missing.append("--step")
        if not args.test:
            missing.append("--test")
        if not args.file_expected:
            missing.append("--file-expected")
        if missing:
            parser.error("create-plan requires --from-file or " + ", ".join(missing))
    if args.command == "record-report":
        if args.kind == "implementation":
            if not args.summary or not args.outcome:
                parser.error("implementation reports require --summary and --outcome")
        elif args.kind == "review":
            if not args.reviewer_role or not args.verdict:
                parser.error("review reports require --reviewer-role and --verdict")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
