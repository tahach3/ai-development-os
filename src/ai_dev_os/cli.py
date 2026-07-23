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
from .orchestration_config import OrchestrationConfigError, load_orchestration_config
from .orchestration_engine import OrchestrationEngine, OrchestrationError
from .orchestration_models import next_allowed_orch_action
from .orchestration_store import OrchestrationStore, OrchestrationStoreError
from .plan_store import PlanStore
from .project_registry import ProjectRegistry, ProjectRegistryError, example_registry_path
from .provider_config import load_provider_config
from .provider_models import ProviderMode, SimulatedFixture
from .provider_runner import ProviderRunner
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
        "workspace/reports/canonical",
        "workspace/reports/rendered",
        "workspace/reports/manifests",
        "workspace/provider_readiness",
        "workspace/handoffs",
        "workspace/context",
        "workspace/plans",
        "workspace/repair_rounds",
        "workspace/sessions",
        "workspace/executions",
        "workspace/orchestrations",
        "workspace/provider_executions",
        "workspace/ci_runs",
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
    ci_run = None
    if getattr(args, "ci_run_file", None):
        from .ci_models import CIRun

        raw = json.loads(Path(args.ci_run_file).read_text(encoding="utf-8"))
        ci_run = CIRun.from_dict(raw)
    orch_summaries = None
    if getattr(args, "include_orchestration", False):
        store = OrchestrationStore()
        orch_summaries = []
        for oid in store.list_ids():
            try:
                orch_summaries.append(store.load(oid).to_dict())
            except Exception:  # noqa: BLE001
                continue
    report = generate_behavioral_report(
        tasks, ci_run=ci_run, orchestration_summaries=orch_summaries
    )
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
                orch_store = OrchestrationStore()
                active_orch = orch_store.find_active_for_task(t.id)
                if active_orch:
                    print(f"      active_orchestration_id: {active_orch.orchestration_id}")
                    print(f"      orch_state: {active_orch.current_state}")
                    print(f"      orch_round: {active_orch.current_round_number}")
                    print(f"      orch_repair_count: {active_orch.current_repair_round}")
                    print(f"      orch_test_status: {active_orch.test_status}")
                    print(f"      orch_review_verdict: {active_orch.review_verdict or 'none'}")
                    print(f"      orch_progress_status: {active_orch.progress_status}")
                    print(f"      orch_stalemate_status: {active_orch.stalemate_status}")
                    print(
                        f"      orch_blocker: {active_orch.stop_reason or 'none'}"
                    )
                    print(
                        "      orch_next_allowed_action: "
                        f"{next_allowed_orch_action(active_orch.state())}"
                    )
                else:
                    print("      active_orchestration_id: none")
            except Exception as exc:  # status-only
                print(f"      orchestration: unavailable ({exc})")
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


def _provider_runner() -> ProviderRunner:
    return ProviderRunner()


def cmd_list_provider_adapters(_args: argparse.Namespace) -> int:
    rows = _provider_runner().list_adapters()
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


def cmd_show_provider_capabilities(args: argparse.Namespace) -> int:
    try:
        caps = _provider_runner().show_capabilities(args.provider)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(caps, indent=2, sort_keys=True))
    return 0


def cmd_discover_providers(_args: argparse.Namespace) -> int:
    results = _provider_runner().discover_all()
    # Ensure no auth material — discovery dicts are already sanitized.
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


def cmd_show_provider_config(_args: argparse.Namespace) -> int:
    cfg = load_provider_config()
    print(json.dumps(cfg.sanitized_public_dict(), indent=2, sort_keys=True))
    return 0


def cmd_validate_provider_request(args: argparse.Namespace) -> int:
    runner = _provider_runner()
    try:
        req = runner.audit_store.load_request(args.request_id)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    result = runner.validate_request(req)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


def cmd_preview_provider_invocation(args: argparse.Namespace) -> int:
    runner = _provider_runner()
    try:
        if args.request_id:
            req = runner.audit_store.load_request(args.request_id)
        else:
            req = runner.build_request(
                provider_id=args.provider,
                task_id=args.task_id,
                plan_id=args.plan_id,
                session_id=args.session_id,
                role=args.role,
                invocation_mode=ProviderMode(args.mode),
                fixture_id=args.fixture,
            )
        preview = runner.preview_invocation(req)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(preview, indent=2, sort_keys=True))
    return 0


def cmd_run_simulated_provider(args: argparse.Namespace) -> int:
    runner = _provider_runner()
    try:
        req = runner.build_request(
            provider_id="simulated",
            task_id=args.task_id,
            plan_id=args.plan_id,
            session_id=args.session_id,
            role=args.role,
            invocation_mode=ProviderMode.SIMULATED,
            fixture_id=args.fixture or SimulatedFixture.SUCCESS_IMPL.value,
            timeout_seconds=args.timeout,
            output_limit_bytes=args.output_limit,
            request_id=args.request_id,
        )
        # Ensure simulated provider is enabled for this operator command via temp overlay
        # only if config already enables it; otherwise refuse (fail closed).
        envelope = runner.run_simulated(req, fixture_id=args.fixture)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"request_id: {envelope.request_id}")
    print(f"policy_decision: {envelope.policy_decision.value}")
    print(f"provider_result_status: {envelope.provider_result_status.value}")
    print(f"failure_class: {envelope.failure_class.value}")
    print(f"automation_status: {envelope.automation_status}")
    if envelope.rejection_reason:
        print(f"rejection_reason: {envelope.rejection_reason}")
    if args.json:
        print(json.dumps(envelope.to_dict(), indent=2, sort_keys=True))
    return 0 if envelope.provider_result_status.value == "success" else 1


def cmd_show_provider_status(args: argparse.Namespace) -> int:
    try:
        status = _provider_runner().show_status(args.request_id)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


def cmd_show_provider_result(args: argparse.Namespace) -> int:
    try:
        envelope = _provider_runner().show_result(args.request_id)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(envelope.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_cancel_provider_execution(args: argparse.Namespace) -> int:
    try:
        result = _provider_runner().cancel(args.request_id)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _orchestration_engine() -> OrchestrationEngine:
    # Prefer on-disk config; fall back only for missing file with fail-closed defaults
    # is not allowed — load must succeed for operator CLI.
    from .provider_config import fail_closed_default_config, ProviderEntryConfig

    orch_cfg = load_orchestration_config()
    pcfg = fail_closed_default_config()
    pcfg.providers["simulated"] = ProviderEntryConfig(
        provider_id="simulated",
        mode=ProviderMode.SIMULATED,
        enabled=True,
        allow_live=False,
    )
    return OrchestrationEngine(orch_config=orch_cfg, provider_config=pcfg)


def cmd_create_orchestration(args: argparse.Namespace) -> int:
    try:
        engine = _orchestration_engine()
        record = engine.create(
            task_id=args.task_id,
            plan_id=args.plan_id,
            session_id=args.session_id,
            scenario_id=args.scenario,
            orchestration_id=args.orchestration_id,
        )
    except (ValidationError, OrchestrationConfigError, OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(engine.status(record.orchestration_id), indent=2, sort_keys=True))
    return 0


def cmd_validate_orchestration(args: argparse.Namespace) -> int:
    try:
        result = _orchestration_engine().validate(args.orchestration_id)
    except (OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


def cmd_preview_orchestration(args: argparse.Namespace) -> int:
    try:
        result = _orchestration_engine().preview(args.orchestration_id)
    except (OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_orchestration_step(args: argparse.Namespace) -> int:
    try:
        engine = _orchestration_engine()
        record = engine.step(args.orchestration_id)
    except (ValidationError, OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(engine.status(record.orchestration_id), indent=2, sort_keys=True))
    return 0


def cmd_run_orchestration(args: argparse.Namespace) -> int:
    try:
        engine = _orchestration_engine()
        record = engine.run_until_boundary(args.orchestration_id, max_steps=args.max_steps)
    except (ValidationError, OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(engine.status(record.orchestration_id), indent=2, sort_keys=True))
    return 0


def cmd_resume_orchestration(args: argparse.Namespace) -> int:
    try:
        engine = _orchestration_engine()
        record = engine.resume(args.orchestration_id)
    except (ValidationError, OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(engine.status(record.orchestration_id), indent=2, sort_keys=True))
    return 0


def cmd_show_orchestration(args: argparse.Namespace) -> int:
    try:
        result = _orchestration_engine().status(args.orchestration_id)
    except (OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_orchestration_history(args: argparse.Namespace) -> int:
    try:
        result = _orchestration_engine().history(args.orchestration_id)
    except (OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_show_stalemate_evidence(args: argparse.Namespace) -> int:
    try:
        result = _orchestration_engine().stalemate_evidence(args.orchestration_id)
    except (OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_cancel_orchestration(args: argparse.Namespace) -> int:
    try:
        engine = _orchestration_engine()
        record = engine.cancel(args.orchestration_id, reason=args.reason or "operator cancel")
    except (ValidationError, OrchestrationStoreError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(engine.status(record.orchestration_id), indent=2, sort_keys=True))
    return 0


def cmd_ci_check(args: argparse.Namespace) -> int:
    from .ci_engine import CIEngineError, ci_run_to_json, exit_code_for_run, run_ci_check
    from .ci_config import CIConfigError

    skip = list(args.skip_stages or [])
    only = list(args.only_stages or []) or None
    try:
        run = run_ci_check(
            skip_stages=skip,
            only_stages=only,
            base_commit=args.base,
            require_clean=bool(args.require_clean) or None,
            persist=bool(args.persist) or None,
            isolate_flaky=bool(getattr(args, "isolate_flaky", False)),
            coverage=bool(getattr(args, "coverage", False)),
        )
    except (CIEngineError, CIConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "format", "json") == "md":
        from .ci_report import render_ci_summary

        artifact = f"workspace/ci_runs/{run.run_id}.json" if bool(args.persist) else None
        print(render_ci_summary(run, artifact_path=artifact), end="")
    else:
        print(ci_run_to_json(run), end="")
    return exit_code_for_run(run)


def cmd_ci_targeted(args: argparse.Namespace) -> int:
    """Round 4F: targeted pytest fast-signal vs a base ref (not authoritative)."""
    from .ci_engine import ci_run_to_json
    from .ci_config import CIConfigError
    from .ci_targeted import CITargetedError, exit_code_for_targeted, run_ci_targeted

    try:
        run = run_ci_targeted(
            base=args.base,
            isolate_flaky=bool(getattr(args, "isolate_flaky", False)),
            persist=bool(getattr(args, "persist", False)) or None,
        )
    except (CITargetedError, CIConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "format", "json") == "md":
        from .ci_report import render_ci_summary

        artifact = f"workspace/ci_runs/{run.run_id}.json" if bool(getattr(args, "persist", False)) else None
        print(render_ci_summary(run, artifact_path=artifact), end="")
    else:
        print(ci_run_to_json(run), end="")
    return exit_code_for_targeted(run)


def cmd_ci_history(args: argparse.Namespace) -> int:
    """List persisted CI runs (most recent first)."""
    from .ci_history import list_runs

    entries = list_runs(_repo_root(), limit=args.limit)
    print(json.dumps([e.to_dict() for e in entries], indent=2, sort_keys=True))
    return 0


def cmd_ci_compare(args: argparse.Namespace) -> int:
    """Compare two persisted CI runs and report regressions deterministically."""
    from .ci_history import compare_runs, compare_to_previous, load_run

    root = _repo_root()
    if args.against_previous:
        comparison = compare_to_previous(root)
        if comparison is None:
            print("ERROR: need at least two persisted runs to compare", file=sys.stderr)
            return 2
    else:
        if not args.base or not args.head:
            print(
                "ERROR: ci-compare requires --base and --head run ids (or --against-previous)",
                file=sys.stderr,
            )
            return 2
        base = load_run(root, args.base)
        head = load_run(root, args.head)
        if base is None or head is None:
            print("ERROR: run id not found in workspace/ci_runs", file=sys.stderr)
            return 2
        comparison = compare_runs(base, head)
    if getattr(args, "format", "json") == "md":
        from .ci_report import render_comparison

        print(render_comparison(comparison.to_dict()), end="")
    else:
        print(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
    return 1 if comparison.regressed else 0


def cmd_validate_change(args: argparse.Namespace) -> int:
    from .ci_validate_change import (
        ValidateChangeError,
        exit_code_for_pr_summary,
        validate_change,
    )
    from .ci_config import CIConfigError

    try:
        summary = validate_change(base=args.base, head=args.head or "HEAD")
    except (ValidateChangeError, CIConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return exit_code_for_pr_summary(summary)


def cmd_ci_boundaries(args: argparse.Namespace) -> int:
    """Round 4E: local multi-project boundary check (not a ci-check stage)."""
    from .ci_boundaries import check_project_boundaries
    from .ci_config import CIConfigError, load_ci_policy
    from .ci_validate_change import ValidateChangeError, _git_name_status

    root = _repo_root()
    try:
        policy = load_ci_policy(root / "config" / "ci_policy.yaml")
        explicit = [p for p in (args.path or []) if p]
        if explicit:
            paths = explicit
        else:
            rows = _git_name_status(root, args.base, args.head or "HEAD")
            paths = [p for _, p in rows]
        result = check_project_boundaries(
            paths=paths,
            policy=policy,
            repo_root=root,
            read_content=True,
        )
    except (CIConfigError, ValidateChangeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


def cmd_provider_readiness(args: argparse.Namespace) -> int:
    """Safe live-provider eligibility audit — never sends model prompts."""
    from .provider_readiness_engine import ProviderReadinessEngine
    from .provider_readiness_reporting import human_summary, render_all_audiences
    from .provider_readiness_staleness import evaluate_staleness, validate_record_structure
    from .provider_readiness_store import ProviderReadinessStore
    from .safe_policy import PolicyError

    try:
        registry = ProjectRegistry()
        engine = ProviderReadinessEngine(registry=registry)
        store = ProviderReadinessStore()

        if args.validate:
            record = store.load_record(args.validate)
            errors = validate_record_structure(record.to_dict())
            from .provider_readiness_engine import _git_head
            from .provider_readiness_profiles import adapter_version_for

            current = evaluate_staleness(
                record,
                repository_commit=_git_head(_repo_root()),
                adapter_version=adapter_version_for(record.provider_id),
                executable_fingerprint=record.executable_fingerprint,
            )
            payload = {
                "valid": not errors,
                "structure_errors": errors,
                "stale_vs_current": current.to_dict(),
                "live_provider_invocations": 0,
                "record": record.to_dict(),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if not errors else 1

        if getattr(args, "validate_pin", None):
            from .provider_readiness_pins import ProviderPinStore, validate_pin
            from .provider_readiness_profiles import adapter_version_for

            provider_id = args.validate_pin
            pin = ProviderPinStore().load(provider_id)
            if pin is None:
                print(json.dumps({"valid": False, "status": "missing", "provider_id": provider_id}))
                return 1
            result = validate_pin(pin, adapter_version=adapter_version_for(provider_id))
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return 0 if result.valid else 1

        if getattr(args, "write_pin", None):
            from .provider_readiness_pins import ProviderPinStore, create_pin
            from .provider_readiness_profiles import adapter_version_for
            from .provider_readiness_selection import validate_approval_phrase

            if not args.candidate_id or not args.executable_path or not args.fingerprint:
                print(
                    "ERROR: --write-pin requires --candidate-id, --executable-path, and --fingerprint",
                    file=sys.stderr,
                )
                return 1
            if not args.approval_phrase or not validate_approval_phrase(
                args.approval_phrase, args.candidate_id
            ):
                print("ERROR: approval phrase mismatch", file=sys.stderr)
                return 1
            if not args.confirm_live_disabled:
                print(
                    "ERROR: --confirm-live-disabled is required to write a pin",
                    file=sys.stderr,
                )
                return 1
            pin = create_pin(
                provider_id=args.write_pin,
                candidate_id=args.candidate_id,
                canonical_executable_path=args.executable_path,
                expected_fingerprint=args.fingerprint,
                adapter_id=args.write_pin,
                adapter_version=adapter_version_for(args.write_pin),
                approval_phrase=args.approval_phrase,
                expected_cli_version=args.expected_cli_version,
                decision_id=args.decision_id,
            )
            path = ProviderPinStore().save(pin)
            print(
                json.dumps(
                    {
                        "stored": str(path),
                        "pin": pin.to_public_dict(),
                        "live_mode_enabled": False,
                        "live_provider_invocations": 0,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if not args.project_id:
            print("ERROR: --project-id is required unless --validate/--validate-pin/--write-pin", file=sys.stderr)
            return 1

        providers = [args.provider] if args.provider else None
        bundle = engine.audit_all(
            project_id=args.project_id,
            providers=providers,
            include_help_summary=bool(args.include_help_summary)
            or bool(getattr(args, "verify_noninteractive_contract", False)),
            allow_unknown_auth_conditional=bool(args.allow_unknown_auth_conditional),
            verify_noninteractive_contract=bool(
                getattr(args, "verify_noninteractive_contract", False)
            ),
        )

        if getattr(args, "generate_selection_record", False):
            from .provider_readiness_selection import OperatorDecisionStore

            decision_store = OperatorDecisionStore()
            saved = []
            for rec in bundle.provider_records:
                decision = (rec.metadata or {}).get("operator_decision")
                if decision:
                    from .provider_readiness_selection import OperatorDecisionRecord

                    record = OperatorDecisionRecord.from_dict(decision)
                    saved.append(str(decision_store.save(record)))
            if args.json:
                print(
                    json.dumps(
                        {"saved": saved, "live_provider_invocations": 0},
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                for p in saved:
                    print(f"selection_record: {p}")
            if not saved and not args.json:
                print("No operator selection records required.")

        out_path = store.save_bundle(bundle)
        reports = render_all_audiences(bundle)

        if args.output:
            Path(args.output).write_text(
                json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        # Ambiguity / candidate views
        extra: dict = {"live_provider_invocations": 0}
        if getattr(args, "show_candidates", False) or getattr(args, "explain_ambiguity", False) or getattr(args, "show_logical_installations", False):
            views = []
            for rec in bundle.provider_records:
                amb = (rec.metadata or {}).get("ambiguity_resolution") or {}
                entry = {"provider_id": rec.provider_id}
                if getattr(args, "show_candidates", False):
                    entry["candidates"] = amb.get("candidates") or rec.candidate_executables
                if getattr(args, "explain_ambiguity", False):
                    entry["ambiguity"] = {
                        "resolved": amb.get("resolved"),
                        "collapse_rule_id": amb.get("collapse_rule_id"),
                        "requires_operator_selection": amb.get("requires_operator_selection"),
                        "note": amb.get("note"),
                        "rejection_reasons": amb.get("rejection_reasons"),
                        "operator_decision": (rec.metadata or {}).get("operator_decision"),
                    }
                if getattr(args, "show_logical_installations", False):
                    entry["logical_installations"] = amb.get("logical_installations")
                views.append(entry)
            extra["ambiguity_views"] = views

        if args.json:
            payload = bundle.to_dict()
            payload["stored_path"] = str(out_path)
            payload.update(extra)
            if args.show_combinations:
                payload["combinations_only"] = [c.to_dict() for c in bundle.combinations]
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(human_summary(bundle))
            if extra.get("ambiguity_views"):
                print("## Ambiguity / candidates")
                print(json.dumps(extra["ambiguity_views"], indent=2, sort_keys=True))
            if args.show_combinations:
                print("## Recommended combinations")
                for c in bundle.combinations:
                    mark = " *" if c.recommended else ""
                    print(
                        f"- {c.category}: {c.implementer_provider_id}/"
                        f"{c.reviewer_provider_id} [{c.independence_status}]{mark}"
                    )
                    print(f"  {c.notes}")
            if getattr(args, "show_host_system_verdict", False):
                print(f"host_system_verdict: {bundle.host_system_verdict}")
            if args.audience:
                print(reports.get(args.audience, ""))
            print(f"stored: {out_path}")
            print("live_provider_invocations: 0")
            print(f"host_system_verdict: {bundle.host_system_verdict}")
        return 0
    except (PolicyError, ProjectRegistryError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_build_report(args: argparse.Namespace) -> int:
    from . import __version__ as pkg_version
    from .reporting_builder import ReportingBuildError
    from .reporting_cli import ReportingCLIError, build_and_persist, load_bundle
    from .reporting_models import DetailLevel, ReportAudience

    try:
        bundle = load_bundle(Path(args.evidence_bundle))
        if args.project_id:
            bundle.project_id = args.project_id
        if args.task_id:
            bundle.task_id = args.task_id
        if args.orchestration_id:
            bundle.orchestration_id = args.orchestration_id
        audience = ReportAudience(args.audience)
        detail = DetailLevel(args.detail_level)
        ws = Path(args.workspace) if args.workspace else None
        snapshot = build_and_persist(
            bundle,
            audience=audience,
            detail_level=detail,
            workspace_root=ws,
            producer_version=pkg_version,
        )
    except (ReportingBuildError, ReportingCLIError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = {
        "report_id": snapshot.report_id,
        "report_status": snapshot.report_status.value,
        "report_fingerprint": snapshot.report_fingerprint,
        "source_set_fingerprint": snapshot.source_set_fingerprint,
        "audience": snapshot.audience.value,
        "detail_level": snapshot.detail_level.value,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_render_report(args: argparse.Namespace) -> int:
    from .reporting_cli import ReportingCLIError, render_and_persist
    from .reporting_models import DetailLevel, ReportAudience
    from .reporting_store import CanonicalReportStore

    try:
        ws = Path(args.workspace) if args.workspace else None
        store = CanonicalReportStore(workspace_root=ws)
        snapshot = store.load_canonical(args.report_id)
        if args.audience:
            snapshot.audience = ReportAudience(args.audience)
        if args.detail_level:
            snapshot.detail_level = DetailLevel(args.detail_level)
        current = None
        if args.current_bindings:
            current = json.loads(Path(args.current_bindings).read_text(encoding="utf-8"))
        md, path = render_and_persist(
            snapshot,
            workspace_root=ws,
            allow_incomplete_diagnostic=bool(args.allow_incomplete_diagnostic),
            current_bindings=current,
        )
    except (ReportingCLIError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
    if args.json:
        print(json.dumps({"report_id": snapshot.report_id, "path": str(path)}, indent=2))
    else:
        print(md)
    return 0


def cmd_validate_report(args: argparse.Namespace) -> int:
    from .reporting_store import CanonicalReportStore
    from .reporting_validate import validate_snapshot

    ws = Path(args.workspace) if args.workspace else None
    store = CanonicalReportStore(workspace_root=ws)
    try:
        snapshot = store.load_canonical(args.report_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    current = None
    if args.current_bindings:
        current = json.loads(Path(args.current_bindings).read_text(encoding="utf-8"))
    result = validate_snapshot(
        snapshot,
        current_bindings=current,
        allow_incomplete_diagnostic=bool(args.allow_incomplete_diagnostic),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


def cmd_show_report(args: argparse.Namespace) -> int:
    from .reporting_store import CanonicalReportStore

    ws = Path(args.workspace) if args.workspace else None
    store = CanonicalReportStore(workspace_root=ws)
    try:
        snapshot = store.load_canonical(args.report_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json" or args.json:
        # Safe summary — no raw evidence structured dumps of secrets
        safe = {
            "report_id": snapshot.report_id,
            "report_status": snapshot.report_status.value,
            "audience": snapshot.audience.value,
            "detail_level": snapshot.detail_level.value,
            "task_id": snapshot.task_id,
            "project_id": snapshot.project_id,
            "outcome": snapshot.outcome,
            "final_verdict": snapshot.final_verdict,
            "blockers": snapshot.blockers,
            "report_fingerprint": snapshot.report_fingerprint,
            "source_set_fingerprint": snapshot.source_set_fingerprint,
            "unavailable_mandatory": snapshot.unavailable_mandatory,
            "evidence_ids": [e.evidence_id for e in snapshot.evidence_manifest],
            "executive_summary": snapshot.executive_summary,
        }
        print(json.dumps(safe, indent=2, sort_keys=True))
    else:
        print(f"report_id={snapshot.report_id}")
        print(f"status={snapshot.report_status.value}")
        print(f"task_id={snapshot.task_id}")
        print(f"outcome={snapshot.outcome}")
        print(f"blockers={len(snapshot.blockers)}")
        print(f"fingerprint={snapshot.report_fingerprint}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-dev-os",
        description="AI Development Operating System (Round 4D1)",
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
    p_beh.add_argument(
        "--ci-run-file",
        default=None,
        help="Optional sanitized CI run JSON to include aggregates",
    )
    p_beh.add_argument(
        "--include-orchestration",
        action="store_true",
        help="Include sanitized orchestration stop/provider aggregates",
    )
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

    p_lpa = sub.add_parser(
        "list-provider-adapters",
        help="List provider adapters and sanitized capabilities",
    )
    p_lpa.set_defaults(func=cmd_list_provider_adapters)

    p_spc = sub.add_parser(
        "show-provider-capabilities",
        help="Show capabilities for one provider adapter",
    )
    p_spc.add_argument("--provider", required=True)
    p_spc.set_defaults(func=cmd_show_provider_capabilities)

    p_dp = sub.add_parser(
        "discover-providers",
        help="Safely discover installed provider CLIs (version/help only)",
    )
    p_dp.set_defaults(func=cmd_discover_providers)

    p_spcfg = sub.add_parser(
        "show-provider-config",
        help="Show sanitized provider configuration (fail-closed defaults)",
    )
    p_spcfg.set_defaults(func=cmd_show_provider_config)

    p_vpr = sub.add_parser(
        "validate-provider-request",
        help="Validate bindings and gates for a stored provider request",
    )
    p_vpr.add_argument("--request-id", required=True)
    p_vpr.set_defaults(func=cmd_validate_provider_request)

    p_ppi = sub.add_parser(
        "preview-provider-invocation",
        help="Preview sanitized provider argv (no live model call)",
    )
    p_ppi.add_argument("--request-id")
    p_ppi.add_argument("--provider")
    p_ppi.add_argument("--task-id")
    p_ppi.add_argument("--plan-id")
    p_ppi.add_argument("--session-id")
    p_ppi.add_argument("--role", choices=["claude", "cursor", "codex"])
    p_ppi.add_argument(
        "--mode",
        default=ProviderMode.SIMULATED.value,
        choices=[m.value for m in ProviderMode],
    )
    p_ppi.add_argument("--fixture", default=None)
    p_ppi.set_defaults(func=cmd_preview_provider_invocation)

    p_rsp = sub.add_parser(
        "run-simulated-provider",
        help="Run deterministic simulated provider (fixtures only; no live model call)",
    )
    p_rsp.add_argument("--task-id", required=True)
    p_rsp.add_argument("--plan-id", required=True)
    p_rsp.add_argument("--session-id", required=True)
    p_rsp.add_argument("--role", choices=["claude", "cursor", "codex"])
    p_rsp.add_argument(
        "--fixture",
        default=SimulatedFixture.SUCCESS_IMPL.value,
        choices=[f.value for f in SimulatedFixture],
    )
    p_rsp.add_argument("--request-id", default=None)
    p_rsp.add_argument("--timeout", type=float, default=None)
    p_rsp.add_argument("--output-limit", type=int, default=None)
    p_rsp.add_argument("--json", action="store_true")
    p_rsp.set_defaults(func=cmd_run_simulated_provider)

    p_sps = sub.add_parser(
        "show-provider-status",
        help="Show provider execution status without private prompts",
    )
    p_sps.add_argument("--request-id", required=True)
    p_sps.set_defaults(func=cmd_show_provider_status)

    p_spr = sub.add_parser(
        "show-provider-result",
        help="Show normalized provider result envelope",
    )
    p_spr.add_argument("--request-id", required=True)
    p_spr.set_defaults(func=cmd_show_provider_result)

    p_cpe = sub.add_parser(
        "cancel-provider-execution",
        help="Request cancellation of a provider execution when safely supported",
    )
    p_cpe.add_argument("--request-id", required=True)
    p_cpe.set_defaults(func=cmd_cancel_provider_execution)

    p_co = sub.add_parser(
        "create-orchestration",
        help="Create a bounded simulated orchestration for an approved task",
    )
    p_co.add_argument("--task-id", required=True)
    p_co.add_argument("--plan-id", required=True)
    p_co.add_argument("--session-id", required=True)
    p_co.add_argument("--scenario", default=None, help="Built-in scenario id (simulated)")
    p_co.add_argument("--orchestration-id", default=None)
    p_co.set_defaults(func=cmd_create_orchestration)

    p_vo = sub.add_parser("validate-orchestration", help="Validate orchestration bindings")
    p_vo.add_argument("--orchestration-id", required=True)
    p_vo.set_defaults(func=cmd_validate_orchestration)

    p_po = sub.add_parser(
        "preview-orchestration",
        help="Preview next orchestration step without mutating state",
    )
    p_po.add_argument("--orchestration-id", required=True)
    p_po.set_defaults(func=cmd_preview_orchestration)

    p_os = sub.add_parser("orchestration-step", help="Execute one orchestration step (simulated)")
    p_os.add_argument("--orchestration-id", required=True)
    p_os.set_defaults(func=cmd_orchestration_step)

    p_ro = sub.add_parser(
        "run-orchestration",
        help="Run simulated orchestration until a safety boundary",
    )
    p_ro.add_argument("--orchestration-id", required=True)
    p_ro.add_argument("--max-steps", type=int, default=None)
    p_ro.set_defaults(func=cmd_run_orchestration)

    p_reso = sub.add_parser("resume-orchestration", help="Resume orchestration after revalidating bindings")
    p_reso.add_argument("--orchestration-id", required=True)
    p_reso.set_defaults(func=cmd_resume_orchestration)

    p_sho = sub.add_parser("show-orchestration", help="Show sanitized orchestration status")
    p_sho.add_argument("--orchestration-id", required=True)
    p_sho.set_defaults(func=cmd_show_orchestration)

    p_oh = sub.add_parser("orchestration-history", help="Show orchestration event history")
    p_oh.add_argument("--orchestration-id", required=True)
    p_oh.set_defaults(func=cmd_orchestration_history)

    p_sse = sub.add_parser(
        "show-stalemate-evidence",
        help="Show deterministic stalemate / progress evidence",
    )
    p_sse.add_argument("--orchestration-id", required=True)
    p_sse.set_defaults(func=cmd_show_stalemate_evidence)

    p_cao = sub.add_parser("cancel-orchestration", help="Cancel an active orchestration")
    p_cao.add_argument("--orchestration-id", required=True)
    p_cao.add_argument("--reason", default="operator cancel")
    p_cao.set_defaults(func=cmd_cancel_orchestration)

    p_ci = sub.add_parser(
        "ci-check",
        help="Run deterministic local CI quality gates (Round 4A)",
    )
    p_ci.add_argument(
        "--skip-stages",
        action="append",
        default=[],
        help="Skip a named stage (repeatable); must be a known STAGE_ORDER name",
    )
    p_ci.add_argument(
        "--only-stages",
        action="append",
        default=[],
        help="Run only these stages (repeatable); others skipped",
    )
    p_ci.add_argument("--base", default=None, help="Optional compared base commit (metadata)")
    p_ci.add_argument("--require-clean", action="store_true")
    p_ci.add_argument("--persist", action="store_true", help="Write sanitized result under workspace/ci_runs")
    p_ci.add_argument(
        "--isolate-flaky",
        action="store_true",
        help="Round 4F: on pytest fail, re-run failed node ids once (honesty: fail-then-pass → flaky_test_detected)",
    )
    p_ci.add_argument(
        "--coverage",
        action="store_true",
        help="Round 4F: optional coverage notes only (never affects verdict; needs optional [cov] extra)",
    )
    p_ci.add_argument(
        "--format",
        choices=["json", "md"],
        default="json",
        help="Output format: json (default) or a human-readable markdown summary",
    )
    p_ci.set_defaults(func=cmd_ci_check)

    p_cit = sub.add_parser(
        "ci-targeted",
        help="Round 4F: targeted pytest vs --base (fast signal; full pytest/ci-check remain authoritative)",
    )
    p_cit.add_argument(
        "--base",
        required=True,
        help="Base ref/SHA for changed-file selection (e.g. PR base)",
    )
    p_cit.add_argument(
        "--isolate-flaky",
        action="store_true",
        help="Same honesty-preserving flaky isolation as ci-check",
    )
    p_cit.add_argument(
        "--persist",
        action="store_true",
        help="Write sanitized result under workspace/ci_runs",
    )
    p_cit.add_argument("--format", choices=["json", "md"], default="json")
    p_cit.set_defaults(func=cmd_ci_targeted)

    p_cih = sub.add_parser(
        "ci-history",
        help="List persisted CI runs from workspace/ci_runs (most recent first)",
    )
    p_cih.add_argument("--limit", type=int, default=20, help="Maximum runs to list")
    p_cih.set_defaults(func=cmd_ci_history)

    p_cmp = sub.add_parser(
        "ci-compare",
        help="Compare two persisted CI runs and report regressions (exit 1 if regressed)",
    )
    p_cmp.add_argument("--base", default=None, help="Older run id (baseline)")
    p_cmp.add_argument("--head", default=None, help="Newer run id")
    p_cmp.add_argument(
        "--against-previous",
        action="store_true",
        help="Compare the two most recent persisted runs (previous vs latest)",
    )
    p_cmp.add_argument("--format", choices=["json", "md"], default="json")
    p_cmp.set_defaults(func=cmd_ci_compare)

    p_vc = sub.add_parser(
        "validate-change",
        help="Validate a proposed commit range/diff without executing change code",
    )
    p_vc.add_argument("--base", default=None, help="Base ref (e.g. master); omit for working tree")
    p_vc.add_argument("--head", default="HEAD")
    p_vc.set_defaults(func=cmd_validate_change)

    p_bound = sub.add_parser(
        "ci-boundaries",
        help="Round 4E multi-project boundary check (local; not a ci-check stage)",
    )
    p_bound.add_argument("--base", default=None, help="Base ref for git name-status path list")
    p_bound.add_argument("--head", default="HEAD")
    p_bound.add_argument(
        "--path",
        action="append",
        default=[],
        help="Explicit relative path to check (repeatable; skips git diff when set)",
    )
    p_bound.set_defaults(func=cmd_ci_boundaries)

    p_br = sub.add_parser(
        "build-report",
        help="Build a canonical evidence-first report snapshot (no model)",
    )
    p_br.add_argument(
        "--evidence-bundle",
        required=True,
        help="Path to JSON evidence bundle (persisted/synthetic records)",
    )
    p_br.add_argument("--project-id", default=None)
    p_br.add_argument("--task-id", default=None)
    p_br.add_argument("--orchestration-id", default=None)
    p_br.add_argument(
        "--audience",
        default="developer",
        choices=[
            "executive",
            "operator",
            "developer",
            "independent_reviewer",
            "auditor",
        ],
    )
    p_br.add_argument(
        "--detail-level",
        default="standard",
        choices=["summary", "standard", "full", "audit"],
    )
    p_br.add_argument("--workspace", default=None, help="Workspace root override")
    p_br.set_defaults(func=cmd_build_report)

    p_rrd = sub.add_parser("render-report", help="Render Markdown from a canonical report")
    p_rrd.add_argument("--report-id", required=True)
    p_rrd.add_argument(
        "--audience",
        default=None,
        choices=[
            "executive",
            "operator",
            "developer",
            "independent_reviewer",
            "auditor",
        ],
    )
    p_rrd.add_argument(
        "--detail-level",
        default=None,
        choices=["summary", "standard", "full", "audit"],
    )
    p_rrd.add_argument("--workspace", default=None)
    p_rrd.add_argument("--output", default=None)
    p_rrd.add_argument("--json", action="store_true")
    p_rrd.add_argument("--allow-incomplete-diagnostic", action="store_true")
    p_rrd.add_argument(
        "--current-bindings",
        default=None,
        help="JSON file of current source bindings for freshness checks",
    )
    p_rrd.set_defaults(func=cmd_render_report)

    p_vr = sub.add_parser("validate-report", help="Validate report schema, fingerprints, freshness")
    p_vr.add_argument("--report-id", required=True)
    p_vr.add_argument("--workspace", default=None)
    p_vr.add_argument("--current-bindings", default=None)
    p_vr.add_argument("--allow-incomplete-diagnostic", action="store_true")
    p_vr.set_defaults(func=cmd_validate_report)

    p_shr = sub.add_parser("show-report", help="Show a safe report summary (no secret dumps)")
    p_shr.add_argument("--report-id", required=True)
    p_shr.add_argument("--workspace", default=None)
    p_shr.add_argument("--format", default="text", choices=["text", "json"])
    p_shr.add_argument("--json", action="store_true")
    p_shr.set_defaults(func=cmd_show_report)

    p_prdy = sub.add_parser(
        "provider-readiness",
        help="Safe provider eligibility audit (discovery/version/help/auth-status only; no live prompts)",
    )
    p_prdy.add_argument(
        "--project-id",
        required=False,
        default=None,
        help="Registered project id (required unless --validate)",
    )
    p_prdy.add_argument("--provider", default=None, help="Single provider id (default: all adapters)")
    p_prdy.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_prdy.add_argument("--output", default=None, help="Optional path for JSON bundle copy")
    p_prdy.add_argument("--validate", default=None, help="Validate/stale-check readiness_id")
    p_prdy.add_argument("--show-combinations", action="store_true")
    p_prdy.add_argument("--include-help-summary", action="store_true")
    p_prdy.add_argument(
        "--verify-noninteractive-contract",
        action="store_true",
        help="Assess noninteractive contract from help/adapter/synthetic rules only (never live prompts)",
    )
    p_prdy.add_argument(
        "--show-host-system-verdict",
        action="store_true",
        help="Highlight Round 4D1.2 host/system final verdict enum",
    )
    p_prdy.add_argument(
        "--allow-unknown-auth-conditional",
        action="store_true",
        help="Allow conditional eligibility when auth is unknown (still not live)",
    )
    p_prdy.add_argument(
        "--audience",
        default=None,
        choices=["executive", "operator", "developer", "auditor"],
        help="Also print a readiness audience report",
    )
    p_prdy.add_argument(
        "--show-candidates",
        action="store_true",
        help="Show sanitized executable candidate matrix (Round 4D1.1)",
    )
    p_prdy.add_argument(
        "--explain-ambiguity",
        action="store_true",
        help="Explain ambiguity resolution / operator selection (Round 4D1.1)",
    )
    p_prdy.add_argument(
        "--show-logical-installations",
        action="store_true",
        help="Show logical installation normalization (Round 4D1.1)",
    )
    p_prdy.add_argument(
        "--generate-selection-record",
        action="store_true",
        help="Persist operator decision records when selection is required",
    )
    p_prdy.add_argument(
        "--validate-pin",
        default=None,
        metavar="PROVIDER_ID",
        help="Validate host-local executable pin for provider",
    )
    p_prdy.add_argument(
        "--recheck",
        action="store_true",
        help="Alias for a fresh readiness audit (no live prompts)",
    )
    p_prdy.add_argument(
        "--write-pin",
        default=None,
        metavar="PROVIDER_ID",
        help="Write host-local pin (requires approval phrase + fingerprint; never enables live)",
    )
    p_prdy.add_argument("--candidate-id", default=None)
    p_prdy.add_argument("--executable-path", default=None, help="Private local path for pin write only")
    p_prdy.add_argument("--fingerprint", default=None, help="Expected SHA-256 fingerprint for pin")
    p_prdy.add_argument("--approval-phrase", default=None)
    p_prdy.add_argument("--decision-id", default=None)
    p_prdy.add_argument("--expected-cli-version", default=None)
    p_prdy.add_argument(
        "--confirm-live-disabled",
        action="store_true",
        help="Required with --write-pin; affirms live mode remains disabled",
    )
    p_prdy.set_defaults(func=cmd_provider_readiness)

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
