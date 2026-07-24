"""Constitutional Court — deterministic Article XIV preflight (§9 matrix)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_dev_os.approval import approve_plan, submit_plan
from ai_dev_os.constitutional_court import (
    COURT_RULES_VERSION,
    COURT_SCHEMA_VERSION,
    CourtEvidenceEnvelope,
    CourtFailureClass,
    CourtVerdict,
    court_record_satisfies_approval,
    evaluate_constitutional_court,
    is_major_change,
)
from ai_dev_os.court_store import CourtStore
from ai_dev_os.fingerprints import fingerprint_plan
from ai_dev_os.models import (
    Complexity,
    Plan,
    PlanStatus,
    ProjectRecord,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
)
from ai_dev_os.plan_store import PlanStore
from ai_dev_os.project_registry import ProjectRegistry
from ai_dev_os.task_store import TaskStore
from ai_dev_os.validation import ValidationError, apply_status_transition


FULL_PROHIBITIONS = [
    "equitify_integration",
    "paid_llm_api_calls",
    "executing_generated_code",
    "auto_approve_high_risk",
    "auto_activate_self_improvement",
    "reading_env_secrets",
    "storing_api_keys",
]


def _git_headish() -> str:
    return "a" * 40


@pytest.fixture
def env(tmp_path: Path):
    # Neutral project root — pytest node tmp paths may contain "equitify" in the
    # test name (sentinel); never use that path as a registered project root.
    import tempfile
    import uuid

    proj = Path(tempfile.gettempdir()) / "ai-dev-os-court" / uuid.uuid4().hex
    proj.mkdir(parents=True, exist_ok=True)
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(ProjectRecord(id="calc", name="Calc", root_path=str(proj)))
    ws = tmp_path / "workspace"
    tasks = TaskStore(ws)
    plans = PlanStore(ws)
    courts = CourtStore(ws)
    return {
        "registry": registry,
        "tasks": tasks,
        "plans": plans,
        "courts": courts,
        "ws": ws,
        "tmp": tmp_path,
        "proj": proj,
    }


def _make_task(store: TaskStore, task_id: str = "t1", **kwargs) -> Task:
    data = {
        "id": task_id,
        "title": "Feature",
        "description": "Do a thing with tests",
        "project_id": "calc",
        "task_type": TaskType.FEATURE.value,
        "complexity": Complexity.SMALL.value,
        "risk_level": RiskLevel.LOW.value,
        "acceptance_criteria": ["works", "tests pass"],
        "allowed_paths": ["calculator/ops.py", "tests/test_ops.py"],
    }
    data.update(kwargs)
    return store.create(data)


def _make_plan(store: PlanStore, task: Task, plan_id: str = "p1", **kwargs) -> Plan:
    data = {
        "plan_id": plan_id,
        "task_id": task.id,
        "project_id": task.project_id,
        "planner_agent": "claude",
        "starting_commit": _git_headish(),
        "objective": "Implement feature with tests",
        "assumptions": ["pure"],
        "scope": ["calculator ops only"],
        "prohibited_actions": ["touch equitify", "network calls"],
        "files_expected_to_change": ["calculator/ops.py", "tests/test_ops.py"],
        "implementation_steps": ["edit ops.py", "add tests"],
        "testing_plan": ["pytest -q"],
        "rollback_or_recovery_plan": ["revert commit"],
        "risks": ["none material"],
        "unresolved_questions": [],
        "approval_requirement": "human",
        "risk_level": task.risk_level.value,
    }
    data.update(kwargs)
    return store.create(data)


def _ready_for_approval(env, task: Task, plan: Plan) -> tuple[Task, Plan]:
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    env["tasks"].update(task)
    plan = submit_plan(env["plans"], plan.plan_id)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    env["tasks"].update(task)
    return task, plan


def _full_high_evidence(**kwargs) -> CourtEvidenceEnvelope:
    data = {
        "schema_version": COURT_SCHEMA_VERSION,
        "metrics_declared": ["tests_pass", "ci_check_ok"],
        "safety_impact_declared": False,
    }
    data.update(kwargs)
    return CourtEvidenceEnvelope.from_dict(data)


def test_low_risk_advisory_passthrough(env):
    task = _make_task(env["tasks"], "t-low")
    plan = _make_plan(env["plans"], task, "p-low")
    assert not is_major_change(task, plan, CourtEvidenceEnvelope())
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
    )
    assert rec.required is False
    assert rec.verdict in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES, CourtVerdict.ADVISORY_ONLY)
    assert rec.verdict != CourtVerdict.REJECTED


def test_high_risk_empty_evidence_rejected_insufficient(env):
    task = _make_task(env["tasks"], "t-he", risk_level="high")
    # In-memory incomplete plan (Court evaluates structure; store validation is separate).
    plan = Plan(
        plan_id="p-he",
        task_id=task.id,
        project_id=task.project_id,
        planner_agent="claude",
        starting_commit="",
        objective="risky",
        scope=["x"],
        prohibited_actions=["equitify"],
        files_expected_to_change=["calculator/ops.py"],
        implementation_steps=[],
        testing_plan=[],
        rollback_or_recovery_plan=[],
        risks=[],
        risk_level=RiskLevel.HIGH,
    )
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict is CourtVerdict.REJECTED
    assert CourtFailureClass.INSUFFICIENT_EVIDENCE.value in rec.failure_classes


def test_medium_required_override_insufficient(env):
    task = _make_task(env["tasks"], "t-med", risk_level="medium", acceptance_criteria=[])
    plan = Plan(
        plan_id="p-med",
        task_id=task.id,
        project_id=task.project_id,
        planner_agent="claude",
        starting_commit=_git_headish(),
        objective="medium change",
        scope=["ops"],
        prohibited_actions=["equitify"],
        files_expected_to_change=["calculator/ops.py"],
        implementation_steps=[],
        testing_plan=[],
        rollback_or_recovery_plan=["revert"],
        risks=["low"],
        risk_level=RiskLevel.MEDIUM,
    )
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.required is True
    assert rec.verdict is CourtVerdict.REJECTED
    assert CourtFailureClass.INSUFFICIENT_EVIDENCE.value in rec.failure_classes


def test_malformed_evidence_cli_exit_4(env, monkeypatch, tmp_path: Path):
    from ai_dev_os import court_store as cs_mod
    from ai_dev_os.cli import main

    task = _make_task(env["tasks"], "t-cli")
    plan = _make_plan(env["plans"], task, "p-cli")
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")

    monkeypatch.setattr("ai_dev_os.cli.TaskStore", lambda: env["tasks"])
    monkeypatch.setattr("ai_dev_os.cli.PlanStore", lambda: env["plans"])
    monkeypatch.setattr("ai_dev_os.cli.ProjectRegistry", lambda: env["registry"])
    monkeypatch.setattr(cs_mod, "CourtStore", lambda *a, **k: env["courts"])

    code = main(
        [
            "constitutional-check",
            "--task-id",
            task.id,
            "--plan-id",
            plan.plan_id,
            "--evaluated-by",
            "human",
            "--evidence",
            str(bad),
            "--advisory",
        ]
    )
    assert code == 4


def test_high_risk_self_review_forbidden(env):
    task = _make_task(env["tasks"], "t-sr", risk_level="high")
    plan = _make_plan(
        env["plans"],
        task,
        "p-sr",
        risk_level="high",
        planner_agent="claude",
        prohibited_actions=list(FULL_PROHIBITIONS),
    )
    rec = evaluate_constitutional_court(
        task,
        plan,
        _full_high_evidence(),
        evaluated_by="claude",
        force_required=True,
    )
    assert rec.verdict is CourtVerdict.BLOCKED
    assert CourtFailureClass.SELF_REVIEW_FORBIDDEN.value in rec.failure_classes


def test_equitify_path_rejected_without_reading_content(env, monkeypatch):
    task = _make_task(env["tasks"], "t-eq", risk_level="high")
    eq_path = "equitify-machine/src/core.py"
    plan = _make_plan(
        env["plans"],
        task,
        "p-eq",
        risk_level="high",
        files_expected_to_change=[eq_path, "tests/test_ops.py"],
        prohibited_actions=list(FULL_PROHIBITIONS),
        risks=["boundary"],
        rollback_or_recovery_plan=["revert"],
    )

    read_calls: list[str] = []

    real_read_text = Path.read_text

    def guarded_read_text(self, *args, **kwargs):  # noqa: ANN001
        text = str(self)
        read_calls.append(text)
        if "equitify" in text.lower().replace("\\", "/"):
            raise AssertionError(f"must not read Equitify content: {text}")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    rec = evaluate_constitutional_court(
        task,
        plan,
        _full_high_evidence(),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict is CourtVerdict.REJECTED
    assert CourtFailureClass.EQUITIFY_BOUNDARY.value in rec.failure_classes
    assert not any("equitify" in c.lower() for c in read_calls)


def test_requires_live_model_without_4d2_locked(env):
    task = _make_task(env["tasks"], "t-4d", risk_level="high")
    plan = _make_plan(
        env["plans"],
        task,
        "p-4d",
        risk_level="high",
        prohibited_actions=list(FULL_PROHIBITIONS),
        risks=["provider"],
        rollback_or_recovery_plan=["revert"],
    )
    rec = evaluate_constitutional_court(
        task,
        plan,
        _full_high_evidence(requires_live_model=True, user_authorized_4d2=False),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict is CourtVerdict.REJECTED
    assert CourtFailureClass.LIVE_PROVIDER_LOCKED.value in rec.failure_classes


def test_safety_critical_without_declaration_rejected(env):
    task = _make_task(env["tasks"], "t-sc", risk_level="medium")
    plan = _make_plan(
        env["plans"],
        task,
        "p-sc",
        risk_level="medium",
        files_expected_to_change=["src/ai_dev_os/approval.py"],
    )
    assert is_major_change(task, plan, CourtEvidenceEnvelope())
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(safety_impact_declared=False),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict is CourtVerdict.REJECTED


def test_risk_underclassified_safety_paths(env):
    task = _make_task(env["tasks"], "t-ru", risk_level="low")
    plan = _make_plan(
        env["plans"],
        task,
        "p-ru",
        risk_level="low",
        files_expected_to_change=["src/ai_dev_os/safe_policy.py"],
    )
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(safety_impact_declared=True),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict is CourtVerdict.REJECTED
    assert CourtFailureClass.RISK_UNDERCLASSIFIED.value in rec.failure_classes


def test_high_risk_full_evidence_pass(env):
    task = _make_task(env["tasks"], "t-ok", risk_level="high")
    plan = _make_plan(
        env["plans"],
        task,
        "p-ok",
        risk_level="high",
        prohibited_actions=list(FULL_PROHIBITIONS),
        risks=["regression"],
        rollback_or_recovery_plan=["revert commit", "restore prior plan"],
        implementation_steps=["edit calculator/ops.py", "add unit tests"],
        testing_plan=["pytest -q", "tests pass"],
    )
    rec = evaluate_constitutional_court(
        task,
        plan,
        _full_high_evidence(),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES), (
        rec.failure_classes,
        [f.to_dict() for f in rec.findings],
    )
    assert rec.required is True
    assert len(rec.checks) == 5


def test_plan_fingerprint_change_invalidates_court_for_approval(env):
    task = _make_task(env["tasks"], "t-fp", risk_level="high")
    plan = _make_plan(
        env["plans"],
        task,
        "p-fp",
        risk_level="high",
        prohibited_actions=list(FULL_PROHIBITIONS),
        risks=["x"],
        rollback_or_recovery_plan=["revert"],
        testing_plan=["pytest -q"],
        implementation_steps=["implement", "test"],
    )
    task, plan = _ready_for_approval(env, task, plan)
    rec = evaluate_constitutional_court(
        task,
        plan,
        _full_high_evidence(),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES)
    env["courts"].save(rec)
    assert court_record_satisfies_approval(rec, plan)

    # Mutate plan content → fingerprint changes; old record invalid.
    plan.objective = "CHANGED OBJECTIVE"
    env["plans"].save(plan)
    plan2 = env["plans"].load(plan.plan_id)
    assert not court_record_satisfies_approval(rec, plan2)
    assert env["courts"].latest_passing_for_plan(
        plan2.plan_id, fingerprint_plan(plan2.to_dict())
    ) is None
    with pytest.raises(ValidationError, match="Constitutional Court required"):
        approve_plan(
            env["plans"],
            env["tasks"],
            plan2.plan_id,
            approver="human",
            court_store=env["courts"],
        )


def test_unsupported_schema_and_rules_blocked(env):
    task = _make_task(env["tasks"], "t-ver")
    plan = _make_plan(env["plans"], task, "p-ver")
    bad_schema = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(schema_version="99.0"),
        evaluated_by="human",
        force_advisory=True,
    )
    assert bad_schema.verdict is CourtVerdict.BLOCKED
    assert CourtFailureClass.UNSUPPORTED_SCHEMA_VERSION.value in bad_schema.failure_classes

    bad_rules = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
        court_rules_version="9.9",
    )
    assert bad_rules.verdict is CourtVerdict.BLOCKED
    assert CourtFailureClass.UNSUPPORTED_RULES_VERSION.value in bad_rules.failure_classes


def test_approve_plan_non_major_byte_for_byte_unaffected(env):
    """Non-major approve_plan must not require Court and must not lock court_* keys."""
    task = _make_task(env["tasks"], "t-nm")
    plan = _make_plan(env["plans"], task, "p-nm")
    task, plan = _ready_for_approval(env, task, plan)

    approved = approve_plan(
        env["plans"],
        env["tasks"],
        plan.plan_id,
        approver="human",
        note="ok",
        court_store=env["courts"],
    )
    assert approved.status is PlanStatus.APPROVED
    task2 = env["tasks"].load(task.id)
    assert "court_record_id" not in task2.metadata
    assert "court_content_fingerprint" not in task2.metadata
    # Canonical non-court approval keys still present (pre-Court contract).
    assert task2.metadata["approved_plan_id"] == plan.plan_id
    assert task2.metadata["approved_plan_fingerprint"] == approved.approved_fingerprint
    assert "task_fingerprint_at_approval" in task2.metadata
    assert "starting_commit_at_approval" in task2.metadata


def test_approve_plan_major_requires_matching_court_pass(env):
    task = _make_task(env["tasks"], "t-maj", risk_level="high")
    plan = _make_plan(
        env["plans"],
        task,
        "p-maj",
        risk_level="high",
        prohibited_actions=list(FULL_PROHIBITIONS),
        risks=["x"],
        rollback_or_recovery_plan=["revert"],
        testing_plan=["pytest -q"],
        implementation_steps=["implement", "test"],
    )
    task, plan = _ready_for_approval(env, task, plan)

    with pytest.raises(ValidationError, match="Constitutional Court required"):
        approve_plan(
            env["plans"],
            env["tasks"],
            plan.plan_id,
            approver="human",
            court_store=env["courts"],
        )

    rec = evaluate_constitutional_court(
        task,
        plan,
        _full_high_evidence(),
        evaluated_by="human-operator",
        force_required=True,
    )
    assert rec.verdict in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES)
    env["courts"].save(rec)

    approved = approve_plan(
        env["plans"],
        env["tasks"],
        plan.plan_id,
        approver="human",
        court_store=env["courts"],
    )
    assert approved.status is PlanStatus.APPROVED
    task2 = env["tasks"].load(task.id)
    assert task2.metadata["court_record_id"] == rec.record_id
    assert task2.metadata["court_content_fingerprint"] == rec.content_fingerprint


def test_no_network_in_pure_evaluate(env, monkeypatch):
    import socket

    sock = MagicMock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(socket, "socket", sock)
    monkeypatch.setattr(socket, "create_connection", sock)

    task = _make_task(env["tasks"], "t-net")
    plan = _make_plan(env["plans"], task, "p-net")
    evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
    )
    sock.assert_not_called()


def test_court_schema_constants():
    assert COURT_SCHEMA_VERSION == "14.1"
    assert COURT_RULES_VERSION == "1.0"


def test_constitutional_check_cli_persists(env, monkeypatch, tmp_path: Path):
    from ai_dev_os import court_store as cs_mod
    from ai_dev_os.cli import main

    task = _make_task(env["tasks"], "t-persist")
    plan = _make_plan(env["plans"], task, "p-persist")
    monkeypatch.setattr("ai_dev_os.cli.TaskStore", lambda: env["tasks"])
    monkeypatch.setattr("ai_dev_os.cli.PlanStore", lambda: env["plans"])
    monkeypatch.setattr("ai_dev_os.cli.ProjectRegistry", lambda: env["registry"])
    monkeypatch.setattr(cs_mod, "CourtStore", lambda *a, **k: env["courts"])

    code = main(
        [
            "constitutional-check",
            "--task-id",
            task.id,
            "--plan-id",
            plan.plan_id,
            "--evaluated-by",
            "human",
            "--advisory",
            "--json",
        ]
    )
    assert code == 0
    records = list(env["courts"].root.glob("*.json"))
    assert len(records) == 1
    payload = json.loads(records[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == COURT_SCHEMA_VERSION
    assert payload["verdict"] in (
        CourtVerdict.PASS.value,
        CourtVerdict.PASS_WITH_NOTES.value,
        CourtVerdict.ADVISORY_ONLY.value,
    )


def test_show_court_record_displays_persisted(env, monkeypatch, capsys):
    from ai_dev_os import court_store as cs_mod
    from ai_dev_os.cli import main

    task = _make_task(env["tasks"], "t-show")
    plan = _make_plan(env["plans"], task, "p-show")
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
    )
    env["courts"].save(rec)
    monkeypatch.setattr(cs_mod, "CourtStore", lambda *a, **k: env["courts"])

    code = main(["show-court-record", "--record-id", rec.record_id])
    assert code == 0
    out = capsys.readouterr().out
    assert f"Court record: {rec.record_id}" in out
    assert f"plan_id: {rec.plan_id}" in out
    assert f"plan_fingerprint: {rec.plan_fingerprint}" in out
    assert "verdict:" in out

    code_json = main(["show-court-record", "--record-id", rec.record_id, "--json"])
    assert code_json == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["record_id"] == rec.record_id
    assert payload["plan_fingerprint"] == rec.plan_fingerprint


def test_show_court_record_missing_id_errors(env, monkeypatch, capsys):
    from ai_dev_os import court_store as cs_mod
    from ai_dev_os.cli import main

    monkeypatch.setattr(cs_mod, "CourtStore", lambda *a, **k: env["courts"])
    code = main(["show-court-record", "--record-id", "court_does_not_exist"])
    assert code == 1
    err = capsys.readouterr().err
    assert "Court record not found" in err


def test_court_ci_visibility_notes_format(env):
    task = _make_task(env["tasks"], "t-note")
    plan = _make_plan(env["plans"], task, "p-note")
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
    )
    assert env["courts"].format_ci_visibility_notes() == []
    env["courts"].save(rec)
    notes = env["courts"].format_ci_visibility_notes()
    assert len(notes) == 1
    note = notes[0]
    assert note.startswith("court_record_present:")
    assert f"record_id={rec.record_id}" in note
    assert f"plan_id={rec.plan_id}" in note
    assert f"plan_fingerprint={rec.plan_fingerprint}" in note
    assert f"verdict={rec.verdict.value}" in note


def test_ci_check_court_note_non_blocking(tmp_path: Path):
    """Court note appears when a record exists; final_verdict/exit unchanged."""
    import subprocess
    import textwrap

    from ai_dev_os.ci_engine import exit_code_for_run, run_ci_check
    from ai_dev_os.ci_models import STAGE_ORDER

    assert "court" not in " ".join(STAGE_ORDER)
    assert list(STAGE_ORDER) == list(STAGE_ORDER)  # identity sanity

    root = tmp_path / "ci_court"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "config").mkdir()
    (root / "docs").mkdir()
    (root / "schemas").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "workspace" / "court_records").mkdir(parents=True)
    (root / "src" / "pkg" / "__init__.py").write_text('__version__ = "0.0.1"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "0.0.1"\n', encoding="utf-8"
    )
    (root / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    policy = (Path(__file__).resolve().parents[1] / "config" / "ci_policy.yaml").read_text(
        encoding="utf-8"
    )
    (root / "config" / "ci_policy.yaml").write_text(policy, encoding="utf-8")
    (root / "config" / "projects.example.yaml").write_text("projects: []\n", encoding="utf-8")
    (root / "README.md").write_text("# Temp\nPackage 0.0.1\n", encoding="utf-8")
    (root / "docs" / "ROADMAP.md").write_text("0.0.1\n", encoding="utf-8")
    (root / "docs" / "PROJECT_CHRONICLE.md").write_text("0.0.1\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            name: ci
            on: [push]
            permissions:
              contents: read
            jobs:
              local-ci:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - run: python -m pytest -q
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

    skip = ["pytest_suite"]
    baseline = run_ci_check(root, skip_stages=skip, persist=False)
    baseline_verdict = baseline.final_verdict
    baseline_exit = exit_code_for_run(baseline)
    assert not any("court_record_present" in n for n in baseline.sanitized_notes)

    task = _make_task(TaskStore(root / "workspace"), "t-ci-note")
    plan = _make_plan(PlanStore(root / "workspace"), task, "p-ci-note")
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
    )
    CourtStore(root / "workspace").save(rec)

    with_note = run_ci_check(root, skip_stages=skip, persist=False)
    assert with_note.final_verdict == baseline_verdict
    assert exit_code_for_run(with_note) == baseline_exit
    assert any(
        f"record_id={rec.record_id}" in n and "court_record_present:" in n
        for n in with_note.sanitized_notes
    )
    # Notes must not flip a clean pass into pass_with_notes solely via Court visibility.
    if baseline_verdict == "pass":
        assert with_note.final_verdict == "pass"


def test_validate_change_court_note_non_blocking(tmp_path: Path):
    """validate-change info finding when Court record exists; verdict/exit unchanged."""
    import subprocess
    import textwrap

    from ai_dev_os.ci_models import STAGE_ORDER
    from ai_dev_os.ci_validate_change import exit_code_for_pr_summary, validate_change

    assert "court_record" not in STAGE_ORDER
    assert "constitutional" not in " ".join(STAGE_ORDER)

    root = tmp_path / "vc_court"
    (root / "src").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "workspace" / "court_records").mkdir(parents=True)
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    policy = (Path(__file__).resolve().parents[1] / "config" / "ci_policy.yaml").read_text(
        encoding="utf-8"
    )
    (root / "config" / "ci_policy.yaml").write_text(policy, encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            name: ci
            on: [push]
            permissions:
              contents: read
            jobs:
              local-ci:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "change"], cwd=root, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    baseline = validate_change(root, base=base, head="HEAD")
    baseline_verdict = baseline.final_verdict
    baseline_exit = exit_code_for_pr_summary(baseline)
    assert not any(f.category == "court_record" for f in baseline.findings)

    task = _make_task(TaskStore(root / "workspace"), "t-vc-note")
    plan = _make_plan(PlanStore(root / "workspace"), task, "p-vc-note")
    rec = evaluate_constitutional_court(
        task,
        plan,
        CourtEvidenceEnvelope(),
        evaluated_by="human",
        force_advisory=True,
    )
    CourtStore(root / "workspace").save(rec)

    with_note = validate_change(root, base=base, head="HEAD")
    assert with_note.final_verdict == baseline_verdict
    assert exit_code_for_pr_summary(with_note) == baseline_exit
    court_findings = [f for f in with_note.findings if f.category == "court_record"]
    assert len(court_findings) == 1
    assert court_findings[0].severity == "info"
    assert court_findings[0].blocker is False
    assert court_findings[0].human_review_required is False
    assert court_findings[0].failure_class == ""
    assert f"record_id={rec.record_id}" in court_findings[0].summary
    assert "none" not in with_note.failure_classes
    assert "court_record" not in with_note.failure_classes


def test_package_version_court_visibility():
    from ai_dev_os import __version__

    assert __version__ == "0.8.14"
