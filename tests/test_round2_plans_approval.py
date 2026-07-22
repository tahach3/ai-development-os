"""Round 2: plans, approval, fingerprints, gates, repair, synthetic lifecycle."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from ai_dev_os.approval import approve_plan, reject_plan, submit_plan, apply_plan_content_update
from ai_dev_os.cli import main
from ai_dev_os.fingerprints import fingerprint_plan, fingerprint_task
from ai_dev_os.handoffs import prepare_role_handoff
from ai_dev_os.lifecycle_gates import (
    GateError,
    assert_can_create_plan,
    assert_can_prepare_implementation_handoff,
)
from ai_dev_os.models import (
    ModelRole,
    Plan,
    PlanStatus,
    ProjectRecord,
    RepairRound,
    ReviewFinding,
    ReviewReport,
    ReviewVerdict,
    FindingSeverity,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
    Complexity,
)
from ai_dev_os.plan_store import PlanStore
from ai_dev_os.project_registry import ProjectRegistry, ProjectRegistryError
from ai_dev_os.repair_rounds import RepairRoundStore
from ai_dev_os.review_gate import apply_review_verdict
from ai_dev_os.task_store import TaskStore
from ai_dev_os.validation import ValidationError, apply_status_transition, validate_plan_dict


def _git_init(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@ai-dev-os.local",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "init",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return head


def _task(store: TaskStore, project_id: str, task_id: str = "t1", **kwargs) -> Task:
    data = {
        "id": task_id,
        "title": "Add multiply",
        "description": "Add multiplication with tests",
        "project_id": project_id,
        "task_type": "feature",
        "complexity": "small",
        "risk_level": "low",
        "acceptance_criteria": ["multiply works", "tests pass"],
        "allowed_paths": ["calculator/ops.py", "tests/test_ops.py"],
    }
    data.update(kwargs)
    return store.create(data)


def _plan_payload(task: Task, head: str, plan_id: str = "p1", **kwargs) -> dict:
    data = {
        "plan_id": plan_id,
        "task_id": task.id,
        "project_id": task.project_id,
        "planner_agent": "claude",
        "starting_commit": head,
        "objective": "Add multiply(a,b) with tests",
        "assumptions": ["pure function"],
        "scope": ["calculator ops only"],
        "prohibited_actions": ["touch equitify", "network calls"],
        "files_expected_to_change": ["calculator/ops.py", "tests/test_ops.py"],
        "implementation_steps": ["add multiply", "add tests"],
        "testing_plan": ["pytest -q"],
        "rollback_or_recovery_plan": ["revert commit"],
        "risks": ["none material"],
        "unresolved_questions": [],
        "approval_requirement": "human",
        "risk_level": task.risk_level.value,
    }
    data.update(kwargs)
    return data


@pytest.fixture
def env(tmp_path: Path):
    root = tmp_path / "proj"
    head = _git_init(root)
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(ProjectRecord(id="calc", name="Calc", root_path=str(root)))
    ws = tmp_path / "workspace"
    tasks = TaskStore(ws)
    plans = PlanStore(ws)
    repairs = RepairRoundStore(ws)
    return {
        "root": root,
        "head": head,
        "registry": registry,
        "tasks": tasks,
        "plans": plans,
        "repairs": repairs,
        "ws": ws,
    }


def test_plan_creation_and_validation(env):
    task = _task(env["tasks"], "calc")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    assert_can_create_plan(task)
    plan = env["plans"].create(_plan_payload(task, env["head"]))
    assert plan.status is PlanStatus.DRAFT
    assert plan.content_fingerprint
    validated = validate_plan_dict(plan.to_dict())
    assert validated.plan_id == plan.plan_id


def test_plan_lifecycle_submit_approve_reject(env):
    task = _task(env["tasks"], "calc", task_id="t-life")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(_plan_payload(task, env["head"], plan_id="p-life"))
    plan = submit_plan(env["plans"], plan.plan_id)
    assert plan.status is PlanStatus.READY_FOR_APPROVAL
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    approved = approve_plan(
        env["plans"], env["tasks"], plan.plan_id, approver="human", note="ok"
    )
    assert approved.status is PlanStatus.APPROVED
    assert approved.approved_by == "human"
    assert approved.approved_fingerprint
    task2 = env["tasks"].load(task.id)
    assert task2.status is TaskStatus.APPROVED_FOR_IMPLEMENTATION

    # Rejection path on a new plan
    task_b = _task(env["tasks"], "calc", task_id="t-rej")
    task_b = apply_status_transition(task_b, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task_b)
    plan_b = env["plans"].create(_plan_payload(task_b, env["head"], plan_id="p-rej"))
    submit_plan(env["plans"], plan_b.plan_id)
    rejected = reject_plan(
        env["plans"], plan_b.plan_id, rejected_by="human", reason="scope unclear"
    )
    assert rejected.status is PlanStatus.REJECTED


def test_self_approval_rejected_for_high_risk(env):
    task = _task(env["tasks"], "calc", task_id="t-hr", risk_level="high")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(
        _plan_payload(task, env["head"], plan_id="p-hr", risk_level="high", planner_agent="claude")
    )
    submit_plan(env["plans"], plan.plan_id)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    with pytest.raises(ValidationError, match="Self-approval"):
        approve_plan(env["plans"], env["tasks"], plan.plan_id, approver="claude")


def test_plan_fingerprint_stability(env):
    task = _task(env["tasks"], "calc", task_id="t-fp")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    payload = _plan_payload(task, env["head"], plan_id="p-fp")
    plan = env["plans"].create(payload)
    fp1 = fingerprint_plan(plan.to_dict())
    plan.created_timestamp = "2099-01-01T00:00:00+00:00"
    fp2 = fingerprint_plan(plan.to_dict())
    assert fp1 == fp2


def test_approval_invalidation_after_plan_change(env):
    task = _task(env["tasks"], "calc", task_id="t-inv")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(_plan_payload(task, env["head"], plan_id="p-inv"))
    submit_plan(env["plans"], plan.plan_id)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    approve_plan(env["plans"], env["tasks"], plan.plan_id, approver="human")
    plan = env["plans"].load(plan.plan_id)
    plan.objective = "CHANGED OBJECTIVE"
    updated = apply_plan_content_update(env["plans"], plan)
    assert updated.status is PlanStatus.DRAFT
    assert updated.approved_fingerprint is None


def test_handoff_blocked_before_approval(env):
    task = _task(env["tasks"], "calc", task_id="t-block")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(_plan_payload(task, env["head"], plan_id="p-block"))
    with pytest.raises(GateError, match="approved_for_implementation|implementable|requires"):
        assert_can_prepare_implementation_handoff(task, plan, env["root"])


def test_handoff_permitted_after_approval(env, tmp_path: Path):
    task = _task(env["tasks"], "calc", task_id="t-ok")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(_plan_payload(task, env["head"], plan_id="p-ok"))
    submit_plan(env["plans"], plan.plan_id)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    approve_plan(env["plans"], env["tasks"], plan.plan_id, approver="human")
    task = env["tasks"].load(task.id)
    plan = env["plans"].load(plan.plan_id)
    result = prepare_role_handoff(
        ModelRole.CURSOR, task, env["root"], tmp_path / "handoffs", plan=plan
    )
    assert result.automation_status == "manual_handoff_required"
    text = result.handoff_path.read_text(encoding="utf-8")
    assert "Approved Plan Only" in text
    assert plan.approved_fingerprint in text


def test_starting_commit_mismatch(env):
    task = _task(env["tasks"], "calc", task_id="t-scm")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(_plan_payload(task, env["head"], plan_id="p-scm"))
    submit_plan(env["plans"], plan.plan_id)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    approve_plan(env["plans"], env["tasks"], plan.plan_id, approver="human")
    task = env["tasks"].load(task.id)
    plan = env["plans"].load(plan.plan_id)
    # Advance HEAD while plan still pins the old starting commit.
    (env["root"] / "extra.txt").write_text("n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=env["root"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@ai-dev-os.local",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "advance",
        ],
        cwd=env["root"],
        check=True,
        capture_output=True,
    )
    with pytest.raises(GateError, match="Starting commit mismatch"):
        assert_can_prepare_implementation_handoff(task, plan, env["root"])


def test_clean_worktree_violation(env):
    task = _task(env["tasks"], "calc", task_id="t-dirty")
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = env["plans"].create(_plan_payload(task, env["head"], plan_id="p-dirty"))
    submit_plan(env["plans"], plan.plan_id)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    approve_plan(env["plans"], env["tasks"], plan.plan_id, approver="human")
    task = env["tasks"].load(task.id)
    plan = env["plans"].load(plan.plan_id)
    (env["root"] / "dirty.txt").write_text("x", encoding="utf-8")
    with pytest.raises(GateError, match="Clean-worktree"):
        assert_can_prepare_implementation_handoff(task, plan, env["root"])


def test_review_verdict_transitions(env):
    task = _task(env["tasks"], "calc", task_id="t-rev")
    for status in (
        TaskStatus.READY_FOR_PLANNING,
        TaskStatus.PLANNED,
        TaskStatus.APPROVED_FOR_IMPLEMENTATION,
        TaskStatus.IMPLEMENTING,
        TaskStatus.VALIDATING,
        TaskStatus.READY_FOR_REVIEW,
    ):
        task = apply_status_transition(task, status)
    env["tasks"].update(task)

    passed = apply_review_verdict(
        task,
        ReviewReport(
            task_id=task.id,
            reviewer_role=ModelRole.CODEX,
            verdict=ReviewVerdict.PASS,
        ),
    )
    assert passed.status is TaskStatus.REVIEW_PASSED

    task2 = env["tasks"].load(task.id)
    task2 = apply_status_transition(task2, TaskStatus.READY_FOR_REVIEW)
    with pytest.raises(ValidationError, match="pass_with_notes"):
        apply_review_verdict(
            task2,
            ReviewReport(
                task_id=task.id,
                reviewer_role=ModelRole.CODEX,
                verdict=ReviewVerdict.PASS_WITH_NOTES,
                confirmed_findings=[
                    ReviewFinding(severity=FindingSeverity.MAJOR, summary="bug")
                ],
            ),
        )

    failed = apply_review_verdict(
        task2,
        ReviewReport(
            task_id=task.id,
            reviewer_role=ModelRole.CODEX,
            verdict=ReviewVerdict.CHANGES_REQUIRED,
        ),
    )
    assert failed.status is TaskStatus.REVIEW_FAILED

    task3 = apply_status_transition(failed, TaskStatus.READY_FOR_REVIEW)
    blocked = apply_review_verdict(
        task3,
        ReviewReport(
            task_id=task.id,
            reviewer_role=ModelRole.CODEX,
            verdict=ReviewVerdict.BLOCKED,
            notes="stop",
        ),
    )
    assert blocked.status is TaskStatus.BLOCKED


def test_repair_round_limits(env):
    task = _task(env["tasks"], "calc", task_id="t-repair")
    for status in (
        TaskStatus.READY_FOR_PLANNING,
        TaskStatus.PLANNED,
        TaskStatus.APPROVED_FOR_IMPLEMENTATION,
        TaskStatus.IMPLEMENTING,
        TaskStatus.VALIDATING,
        TaskStatus.READY_FOR_REVIEW,
        TaskStatus.REVIEW_FAILED,
    ):
        task = apply_status_transition(task, status)
    env["tasks"].update(task)

    for i in range(1, 4):
        rnd = RepairRound(
            task_id=task.id,
            round_number=i,
            reason=f"fix {i}",
            result="partial",
        )
        env["repairs"].record(rnd, task_store=env["tasks"], max_rounds=3)
        task = env["tasks"].load(task.id)

    with pytest.raises(ValidationError, match="limit"):
        env["repairs"].record(
            RepairRound(
                task_id=task.id,
                round_number=4,
                reason="too many",
                result="failed",
            ),
            task_store=env["tasks"],
            max_rounds=3,
        )
    task = env["tasks"].load(task.id)
    assert task.status is TaskStatus.BLOCKED


def test_unregistered_and_prohibited_repo_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    with pytest.raises(ProjectRegistryError, match="Unregistered"):
        registry.require("nope")
    with pytest.raises(ProjectRegistryError, match="Equitify"):
        registry.register(
            ProjectRecord(
                id="eq",
                name="Equitify Machine",
                root_path=str(tmp_path / "synthetic-equitify-name"),
            )
        )


def test_full_synthetic_lifecycle(tmp_path: Path, monkeypatch):
    """Exercise create→route→plan→approve→handoff→reports→complete using synthetic dirs."""
    demo = tmp_path / "calculator-demo"
    head = _git_init(demo)
    (demo / "calculator").mkdir()
    (demo / "calculator" / "ops.py").write_text(
        "def add(a,b): return a+b\ndef subtract(a,b): return a-b\n",
        encoding="utf-8",
    )
    (demo / "tests").mkdir()
    (demo / "tests" / "test_ops.py").write_text(
        "from calculator.ops import add\ndef test_add(): assert add(1,1)==2\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=demo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@ai-dev-os.local",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "baseline",
        ],
        cwd=demo,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=demo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    registry_path = tmp_path / "projects.yaml"
    ws = tmp_path / "workspace"
    registry = ProjectRegistry(registry_path)
    registry.register(ProjectRecord(id="calculator-demo", name="Calc Demo", root_path=str(demo)))

    monkeypatch.setattr("ai_dev_os.cli.ProjectRegistry", lambda: ProjectRegistry(registry_path))
    monkeypatch.setattr("ai_dev_os.cli.TaskStore", lambda: TaskStore(ws))
    monkeypatch.setattr("ai_dev_os.cli.PlanStore", lambda: PlanStore(ws))
    monkeypatch.setattr("ai_dev_os.cli.ReportStore", lambda: __import__("ai_dev_os.report_store", fromlist=["ReportStore"]).ReportStore(ws))
    monkeypatch.setattr("ai_dev_os.cli.RepairRoundStore", lambda: RepairRoundStore(ws))
    monkeypatch.setattr(
        "ai_dev_os.cli._repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "ai_dev_os.handoffs.ReportStore",
        lambda: __import__("ai_dev_os.report_store", fromlist=["ReportStore"]).ReportStore(ws),
    )

    assert main([
        "create-task",
        "--project-id", "calculator-demo",
        "--id", "calc-multiply",
        "--title", "Add multiplication",
        "--description", "Add multiply with tests",
        "--task-type", "feature",
        "--complexity", "small",
        "--risk-level", "low",
        "--acceptance", "multiply(2,3)==6",
        "--allowed-path", "calculator/ops.py",
        "--allowed-path", "tests/test_ops.py",
    ]) == 0
    assert main(["set-task-status", "--task-id", "calc-multiply", "--status", "ready_for_planning"]) == 0
    assert main(["route-task", "--task-id", "calc-multiply"]) == 0
    assert main([
        "create-plan",
        "--task-id", "calc-multiply",
        "--plan-id", "plan-multiply",
        "--planner-agent", "claude",
        "--objective", "Add multiply(a,b)",
        "--starting-commit", head,
        "--scope", "calculator module",
        "--prohibited-action", "no equitify",
        "--file-expected", "calculator/ops.py",
        "--file-expected", "tests/test_ops.py",
        "--step", "implement multiply",
        "--step", "add unit test",
        "--test", "pytest -q",
        "--rollback", "git revert",
        "--risk", "low",
    ]) == 0
    assert main(["validate-plan", "--plan-id", "plan-multiply"]) == 0
    assert main(["submit-plan", "--plan-id", "plan-multiply"]) == 0
    assert main([
        "approve-plan",
        "--plan-id", "plan-multiply",
        "--approver", "human-operator",
        "--note", "approved for demo",
    ]) == 0
    assert main(["build-context", "--task-id", "calc-multiply", "--output", str(tmp_path / "ctx")]) == 0
    assert main([
        "prepare-handoff",
        "--task-id", "calc-multiply",
        "--role", "cursor",
        "--output", str(tmp_path / "handoffs"),
    ]) == 0
    # Synthetic implementation (controlled report — not live agent automation)
    (demo / "calculator" / "ops.py").write_text(
        "def add(a,b): return a+b\ndef subtract(a,b): return a-b\ndef multiply(a,b): return a*b\n",
        encoding="utf-8",
    )
    assert main([
        "record-report",
        "--kind", "implementation",
        "--task-id", "calc-multiply",
        "--summary", "Added multiply",
        "--outcome", "success",
        "--file-changed", "calculator/ops.py",
        "--file-changed", "tests/test_ops.py",
        "--test-run", "pytest -q",
    ]) == 0
    assert main([
        "prepare-handoff",
        "--task-id", "calc-multiply",
        "--role", "codex",
        "--output", str(tmp_path / "handoffs"),
        "--allow-dirty",
    ]) == 0
    assert main([
        "record-report",
        "--kind", "review",
        "--task-id", "calc-multiply",
        "--reviewer-role", "codex",
        "--verdict", "pass",
        "--confirmed-finding", "note|looks good",
        "--rejected-finding", "minor|nit ignored",
    ]) == 0
    assert main(["set-task-status", "--task-id", "calc-multiply", "--status", "ready_to_commit"]) == 0
    assert main(["set-task-status", "--task-id", "calc-multiply", "--status", "completed"]) == 0
    monkeypatch.setattr(
        "ai_dev_os.behavioral_metrics._repo_root",
        lambda: tmp_path,
    )
    # behavioral report uses TaskStore default; patch write path via workspace listing
    from ai_dev_os.behavioral_metrics import generate_behavioral_report, write_behavioral_report

    tasks = TaskStore(ws).list_tasks(include_completed=True)
    report = generate_behavioral_report(tasks)
    path = write_behavioral_report(report, tmp_path / "behavioral")
    assert path.exists()
    assert any(t.id == "calc-multiply" and t.status is TaskStatus.COMPLETED for t in tasks)
    assert main(["project-status", "--project-id", "calculator-demo"]) == 0
