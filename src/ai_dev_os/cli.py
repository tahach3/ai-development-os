"""CLI for AI Development Operating System."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .adapters import get_adapter
from .behavioral_metrics import (
    generate_behavioral_report,
    render_behavioral_markdown,
    write_behavioral_report,
)
from .context_builder import build_context_packet, write_context_packet
from .git_safety import inspect_repo
from .models import (
    FindingSeverity,
    ImplementationReport,
    ModelRole,
    ProjectRecord,
    ReportOutcome,
    ReviewFinding,
    ReviewReport,
    ReviewVerdict,
    TaskStatus,
    TokenUsage,
    TokenUsageMode,
)
from .project_registry import ProjectRegistry, ProjectRegistryError, example_registry_path
from .report_store import ReportStore
from .routing import apply_routing, route_task
from .task_store import TaskStore
from .validation import ValidationError, validate_task_dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


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
    try:
        task = store.load(args.task_id)
        if not task.assigned_role:
            task = apply_routing(task)
            store.update(task)
        root = registry.resolve_root(task.project_id)
        role = args.role or task.assigned_role.value
        adapter = get_adapter(role)
        out_dir = Path(args.output) if args.output else (_repo_root() / "workspace" / "handoffs")
        result = adapter.prepare_handoff(task, root, out_dir)
    except (ValidationError, ProjectRegistryError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(result.message)
    print(f"automation_status: {result.automation_status}")
    return 0


def cmd_record_report(args: argparse.Namespace) -> int:
    store = ReportStore()
    try:
        if args.kind == "implementation":
            usage = TokenUsage(
                mode=TokenUsageMode(args.usage_mode),
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
                notes=args.usage_notes,
            )
            # Never fabricate: unavailable clears counts via from_dict semantics.
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
            )
            path = store.save_implementation(report)
        else:
            findings = []
            for raw in args.finding or []:
                # severity|summary[|path]
                parts = raw.split("|", 2)
                if len(parts) < 2:
                    raise ValidationError(
                        "Finding format must be severity|summary or severity|summary|path"
                    )
                findings.append(
                    ReviewFinding(
                        severity=FindingSeverity(parts[0]),
                        summary=parts[1],
                        path=parts[2] if len(parts) > 2 else None,
                    )
                )
            report = ReviewReport(
                task_id=args.task_id,
                reviewer_role=ModelRole(args.reviewer_role),
                verdict=ReviewVerdict(args.verdict),
                findings=findings,
                notes=args.notes,
            )
            path = store.save_review(report)
    except (ValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Recorded {args.kind} report at {path}")
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
    for finding in latest.findings:
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
        print(f"  tasks: {len(related)}")
        by_status: dict[str, int] = {}
        for t in related:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        for status, count in sorted(by_status.items()):
            print(f"    {status}: {count}")
        try:
            inspection = inspect_repo(project.root_path)
            print(
                f"  git: repo={inspection.is_repo} branch={inspection.branch} "
                f"dirty={inspection.dirty}"
            )
        except Exception as exc:  # inspect-only; never mutate
            print(f"  git: inspect failed ({exc})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-dev-os",
        description="AI Development Operating System (Round 1 foundation)",
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

    p_hand = sub.add_parser("prepare-handoff", help="Prepare manual adapter handoff")
    p_hand.add_argument("--task-id", required=True)
    p_hand.add_argument("--role", choices=["claude", "cursor", "codex"])
    p_hand.add_argument("--output")
    p_hand.set_defaults(func=cmd_prepare_handoff)

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
    p_rep.add_argument("--notes", default=None)
    p_rep.set_defaults(func=cmd_record_report)

    p_rev = sub.add_parser("review-status", help="Show latest review status for a task")
    p_rev.add_argument("--task-id", required=True)
    p_rev.set_defaults(func=cmd_review_status)

    p_beh = sub.add_parser("behavioral-report", help="Generate behavioral metrics report")
    p_beh.add_argument("--json", action="store_true")
    p_beh.set_defaults(func=cmd_behavioral_report)

    p_ps = sub.add_parser("project-status", help="Show project and task status")
    p_ps.add_argument("--project-id")
    p_ps.set_defaults(func=cmd_project_status)

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
