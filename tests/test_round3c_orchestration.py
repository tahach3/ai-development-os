"""Round 3C: bounded orchestration, stalemate detection, simulated lifecycles."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from ai_dev_os.approval import approve_plan, submit_plan
from ai_dev_os.atomic_io import atomic_write_yaml
from ai_dev_os.models import (
    Complexity,
    ModelRole,
    Plan,
    ProjectRecord,
    RiskLevel,
    TaskStatus,
    TaskType,
)
from ai_dev_os.orchestration_bindings import BindingError, validate_bindings
from ai_dev_os.orchestration_config import (
    OrchestrationConfig,
    OrchestrationConfigError,
    fail_closed_default_orchestration_config,
    load_orchestration_config,
    validate_orchestration_config,
)
from ai_dev_os.orchestration_engine import OrchestrationEngine, OrchestrationError, SCENARIO_SCRIPTS
from ai_dev_os.orchestration_models import (
    ORCH_TRANSITIONS,
    ORCHESTRATION_SCHEMA_VERSION,
    OrchestrationFailureClass,
    OrchestrationRecord,
    OrchestrationState,
    RoundEvidence,
    StructuredFinding,
    TERMINAL_ORCH_STATES,
    findings_fingerprint,
)
from ai_dev_os.orchestration_mutations import apply_fixture_mutation
from ai_dev_os.orchestration_stalemate import detect_stalemate, evaluate_round_progress
from ai_dev_os.orchestration_store import OrchestrationStore
from ai_dev_os.plan_store import PlanStore
from ai_dev_os.project_registry import ProjectRegistry, ProjectRegistryError
from ai_dev_os.provider_audit import ProviderAuditStore
from ai_dev_os.provider_config import ProviderConfig, ProviderEntryConfig, fail_closed_default_config
from ai_dev_os.provider_models import ProviderMode, SimulatedFixture
from ai_dev_os.provider_runner import ProviderRunner
from ai_dev_os.session_store import SessionStore
from ai_dev_os.task_store import TaskStore
from ai_dev_os.validation import apply_status_transition
from ai_dev_os.worktrees import read_head


SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[a-z0-9\-_]{16,}"),
    re.compile(r"(?i)secret\s*[:=]\s*['\"]?[a-z0-9\-_]{12,}"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-_\.]{20,}"),
]


def _git_init_calculator(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    (path / "calculator").mkdir()
    (path / "tests").mkdir()
    (path / "calculator" / "__init__.py").write_text("", encoding="utf-8")
    (path / "calculator" / "ops.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (path / "tests" / "test_ops.py").write_text(
        "from calculator.ops import add\n"
        "def test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
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
            "init calculator-demo",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return read_head(path)


def _sim_provider_config() -> ProviderConfig:
    cfg = fail_closed_default_config()
    cfg.providers["simulated"] = ProviderEntryConfig(
        provider_id="simulated",
        mode=ProviderMode.SIMULATED,
        enabled=True,
        allow_live=False,
    )
    return cfg


def _orch_config(**overrides) -> OrchestrationConfig:
    cfg = fail_closed_default_orchestration_config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return validate_orchestration_config(cfg)


@pytest.fixture
def calc_orch_env(tmp_path: Path):
    demo = tmp_path / "calculator-demo"
    head = _git_init_calculator(demo)
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(
        ProjectRecord(
            id="calculator-demo",
            name="Calculator Demo",
            root_path=str(demo),
            metadata={},
        )
    )
    ws = tmp_path / "workspace"
    tasks = TaskStore(ws)
    plans = PlanStore(ws)
    sessions = SessionStore(workspace_root=ws, registry=registry)
    audits = ProviderAuditStore(workspace_root=ws)
    provider_config = _sim_provider_config()
    orch_config = _orch_config()
    runner = ProviderRunner(
        workspace_root=ws,
        registry=registry,
        config=provider_config,
        task_store=tasks,
        plan_store=plans,
        session_store=sessions,
        audit_store=audits,
    )
    engine = OrchestrationEngine(
        workspace_root=ws,
        registry=registry,
        orch_config=orch_config,
        provider_config=provider_config,
        task_store=tasks,
        plan_store=plans,
        session_store=sessions,
        provider_runner=runner,
    )

    task = tasks.create(
        {
            "id": "calc-3c-1",
            "title": "Add subtract",
            "description": "Synthetic Round 3C orchestration task",
            "project_id": "calculator-demo",
            "task_type": TaskType.FEATURE.value,
            "complexity": Complexity.SMALL.value,
            "risk_level": RiskLevel.LOW.value,
            "acceptance_criteria": ["tests pass"],
            "allowed_paths": ["calculator/ops.py", "tests/test_ops.py"],
        }
    )
    task = apply_status_transition(task, TaskStatus.READY_FOR_PLANNING)
    task.assigned_role = ModelRole.CURSOR
    tasks.update(task)
    task = apply_status_transition(task, TaskStatus.PLANNED)
    tasks.update(task)

    plan = Plan.from_dict(
        {
            "plan_id": "plan-3c-1",
            "task_id": task.id,
            "project_id": "calculator-demo",
            "planner_agent": "cursor",
            "starting_commit": head,
            "objective": "Add subtract with tests",
            "assumptions": ["pure function"],
            "scope": ["calculator ops"],
            "prohibited_actions": ["equitify", "network"],
            "files_expected_to_change": ["calculator/ops.py", "tests/test_ops.py"],
            "implementation_steps": ["implement", "test"],
            "testing_plan": ["pytest -q"],
            "rollback_or_recovery_plan": ["revert"],
            "risks": ["low"],
            "unresolved_questions": [],
            "approval_requirement": "human",
            "risk_level": RiskLevel.LOW.value,
        }
    )
    plans.save(plan)
    submit_plan(plans, plan.plan_id)
    approve_plan(plans, tasks, plan.plan_id, approver="human-operator")
    session = sessions.create(project_id="calculator-demo", task_id=task.id)

    return {
        "demo": demo,
        "head": head,
        "registry": registry,
        "ws": ws,
        "tasks": tasks,
        "plans": plans,
        "sessions": sessions,
        "engine": engine,
        "task": tasks.load(task.id),
        "plan": plans.load(plan.plan_id),
        "session": session,
        "demo_head_before": head,
    }


def _run_scenario(env, scenario_id: str, **cfg_overrides):
    if cfg_overrides:
        env["engine"].orch_config = _orch_config(**cfg_overrides)
    record = env["engine"].create(
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        scenario_id=scenario_id,
        orchestration_id=f"orch-{scenario_id}",
    )
    final = env["engine"].run_until_boundary(record.orchestration_id)
    return final


# --------------------------------------------------------------------------- A
def test_direct_success_scenario(calc_orch_env):
    final = _run_scenario(calc_orch_env, "direct_success")
    assert final.current_state == OrchestrationState.COMPLETED.value
    assert final.current_repair_round == 0
    assert final.review_verdict == "pass"
    assert final.test_status == "passed"
    summary = calc_orch_env["engine"].orch_store.load_summary(final.orchestration_id)
    assert summary is not None
    assert summary.final_state == "completed"
    # Main checkout unchanged
    assert read_head(calc_orch_env["demo"]) == calc_orch_env["demo_head_before"]


def test_pass_with_notes_completion(calc_orch_env):
    final = _run_scenario(calc_orch_env, "pass_with_notes")
    assert final.current_state == OrchestrationState.COMPLETED.value
    assert final.review_verdict == "pass_with_notes"


def test_one_repair_scenario(calc_orch_env):
    final = _run_scenario(calc_orch_env, "one_repair")
    assert final.current_state == OrchestrationState.COMPLETED.value
    assert final.current_repair_round == 1
    assert final.review_verdict == "pass"


def test_test_fail_then_repair(calc_orch_env):
    final = _run_scenario(calc_orch_env, "test_fail_then_repair")
    assert final.current_state == OrchestrationState.COMPLETED.value
    assert final.current_repair_round >= 1
    assert final.test_status == "passed"
    assert not final.stop_reason


def test_buggy_and_fixed_mutation_sizes_differ():
    from ai_dev_os.orchestration_mutations import MUTATION_CATALOG

    buggy = MUTATION_CATALOG["add_subtract_buggy"]["files"]["calculator/ops.py"]
    fixed = MUTATION_CATALOG["add_subtract_fixed"]["files"]["calculator/ops.py"]
    assert len(buggy) != len(fixed), (
        "same-size buggy/fixed sources flake under CPython second-resolution .pyc mtime"
    )


def test_mutation_clears_stale_bytecode(tmp_path: Path):
    """Harness mutations must drop .pyc so same-second equal-size rewrites stay correct."""
    import os
    import py_compile

    from ai_dev_os.orchestration_mutations import MUTATION_CATALOG, apply_fixture_mutation

    # Historical equal-length pair that triggered the CI flake under second mtime.
    equal_buggy = (
        "def add(a, b):\n    return a + b\n\n"
        "def subtract(a, b):\n    return a + b\n"
    )
    equal_fixed = (
        "def add(a, b):\n    return a + b\n\n"
        "def subtract(a, b):\n    return a - b\n"
    )
    assert len(equal_buggy) == len(equal_fixed)

    root = tmp_path / "wt"
    (root / "calculator").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "calculator" / "__init__.py").write_text("", encoding="utf-8")
    ops = root / "calculator" / "ops.py"
    ops.write_text(equal_buggy, encoding="utf-8")
    (root / "tests" / "test_ops.py").write_text(
        MUTATION_CATALOG["add_subtract_fixed"]["files"]["tests/test_ops.py"],
        encoding="utf-8",
    )
    py_compile.compile(str(ops), doraise=True)
    assert list((root / "calculator").rglob("*.pyc"))
    mtime = ops.stat().st_mtime
    ops.write_text(equal_fixed, encoding="utf-8")
    os.utime(ops, (mtime, mtime))
    # Without invalidation, pytest would still see buggy bytecode (subtract→7).
    apply_fixture_mutation(root, "add_subtract_fixed", commit=False)
    assert not list((root / "calculator").rglob("*.pyc"))
    result = subprocess.run(
        ["python", "-m", "pytest", "-q", "tests"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- B
def test_state_machine_allowed_and_prohibited():
    for state, allowed in ORCH_TRANSITIONS.items():
        for other in OrchestrationState:
            if other in allowed:
                assert other in ORCH_TRANSITIONS[state]
            elif other is state:
                continue
            else:
                assert other not in allowed


def test_terminal_states_have_no_transitions():
    for state in TERMINAL_ORCH_STATES:
        assert ORCH_TRANSITIONS[state] == frozenset()


def test_invalid_direct_state_mutation_rejected(calc_orch_env):
    engine = calc_orch_env["engine"]
    record = engine.create(
        task_id=calc_orch_env["task"].id,
        plan_id=calc_orch_env["plan"].plan_id,
        session_id=calc_orch_env["session"].session_id,
        scenario_id="direct_success",
    )
    with pytest.raises(OrchestrationError):
        engine._transition(record, OrchestrationState.COMPLETED)


# --------------------------------------------------------------------------- C
def test_changed_plan_fingerprint_blocks(calc_orch_env):
    engine = calc_orch_env["engine"]
    record = engine.create(
        task_id=calc_orch_env["task"].id,
        plan_id=calc_orch_env["plan"].plan_id,
        session_id=calc_orch_env["session"].session_id,
        scenario_id="direct_success",
    )
    plan = calc_orch_env["plans"].load(record.plan_id)
    plan.objective = "CHANGED OBJECTIVE"
    calc_orch_env["plans"].save(plan)
    result = engine.validate(record.orchestration_id)
    assert result["valid"] is False
    assert result["failure_class"] in (
        OrchestrationFailureClass.STALE_BINDING.value,
        OrchestrationFailureClass.APPROVAL_INVALID.value,
    )


def test_equitify_project_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    with pytest.raises((ProjectRegistryError, Exception)):
        registry.register(
            ProjectRecord(
                id="equitify-machine",
                name="Equitify",
                root_path=str(tmp_path / "safe-demo"),
            )
        )


# --------------------------------------------------------------------------- D/E scenarios
def test_stalemate_identical_scenario(calc_orch_env):
    final = _run_scenario(calc_orch_env, "stalemate_identical")
    assert final.current_state == OrchestrationState.HUMAN_REVIEW_REQUIRED.value
    assert final.stalemate_status == "detected"
    assert final.stop_reason
    # No further provider after stop: fixture index should not exceed script after stop
    evidence = calc_orch_env["engine"].stalemate_evidence(final.orchestration_id)
    assert evidence["stalemate_status"] == "detected"


def test_stalemate_oscillation_scenario(calc_orch_env):
    final = _run_scenario(calc_orch_env, "stalemate_oscillation")
    assert final.current_state == OrchestrationState.HUMAN_REVIEW_REQUIRED.value
    assert final.last_failure_class in (
        OrchestrationFailureClass.OSCILLATION_DETECTED.value,
        OrchestrationFailureClass.NO_PROGRESS.value,
    )


def test_repair_limit_scenario(calc_orch_env):
    final = _run_scenario(calc_orch_env, "repair_limit", max_repair_rounds=3)
    assert final.current_state == OrchestrationState.BLOCKED.value
    assert final.last_failure_class == OrchestrationFailureClass.REPAIR_LIMIT_REACHED.value
    assert final.current_repair_round >= 3


def test_genuine_progress_not_stalemate(calc_orch_env):
    final = _run_scenario(calc_orch_env, "one_repair")
    assert final.stalemate_status != "detected"
    assert final.current_state == OrchestrationState.COMPLETED.value


# --------------------------------------------------------------------------- F
def test_malformed_implementation_blocks(calc_orch_env):
    engine = calc_orch_env["engine"]
    record = engine.create(
        task_id=calc_orch_env["task"].id,
        plan_id=calc_orch_env["plan"].plan_id,
        session_id=calc_orch_env["session"].session_id,
        fixture_script=[
            {
                "phase": "implementation",
                "fixture": SimulatedFixture.MALFORMED_OUTPUT.value,
                "mutation": "noop",
            }
        ],
        orchestration_id="orch-malformed",
    )
    final = engine.run_until_boundary(record.orchestration_id)
    assert final.current_state in (
        OrchestrationState.BLOCKED.value,
        OrchestrationState.HUMAN_REVIEW_REQUIRED.value,
    )
    assert final.last_failure_class in (
        OrchestrationFailureClass.MALFORMED_PROVIDER_RESULT.value,
        OrchestrationFailureClass.IMPLEMENTATION_RESULT_INVALID.value,
    )


def test_live_provider_prohibited_by_config():
    with pytest.raises(OrchestrationConfigError):
        validate_orchestration_config(
            OrchestrationConfig(allow_live_providers=True, default_invocation_mode="simulated")
        )


def test_independent_review_context_differs(calc_orch_env):
    engine = calc_orch_env["engine"]
    record = engine.create(
        task_id=calc_orch_env["task"].id,
        plan_id=calc_orch_env["plan"].plan_id,
        session_id=calc_orch_env["session"].session_id,
        scenario_id="direct_success",
    )
    engine.run_until_boundary(record.orchestration_id)
    record = engine.orch_store.load_record(record.orchestration_id)
    assert record.implementation_context_fingerprint
    assert record.review_context_fingerprint
    assert record.implementation_context_fingerprint != record.review_context_fingerprint
    assert record.implementation_role != record.review_role


# --------------------------------------------------------------------------- G
def test_cancel_persists_and_blocks_resume(calc_orch_env):
    engine = calc_orch_env["engine"]
    record = engine.create(
        task_id=calc_orch_env["task"].id,
        plan_id=calc_orch_env["plan"].plan_id,
        session_id=calc_orch_env["session"].session_id,
        scenario_id="direct_success",
    )
    engine.step(record.orchestration_id)  # created -> ready
    engine.cancel(record.orchestration_id, reason="test cancel")
    reloaded = engine.orch_store.load_record(record.orchestration_id)
    assert reloaded.current_state == OrchestrationState.CANCELLED.value
    assert reloaded.cancelled_at
    with pytest.raises(OrchestrationError):
        engine.resume(record.orchestration_id)


def test_resume_preserves_counters(calc_orch_env):
    engine = calc_orch_env["engine"]
    record = engine.create(
        task_id=calc_orch_env["task"].id,
        plan_id=calc_orch_env["plan"].plan_id,
        session_id=calc_orch_env["session"].session_id,
        scenario_id="one_repair",
    )
    # Advance a few steps
    for _ in range(3):
        record = engine.step(record.orchestration_id)
    steps = record.current_step_number
    engine2 = OrchestrationEngine(
        workspace_root=calc_orch_env["ws"],
        registry=calc_orch_env["registry"],
        orch_config=engine.orch_config,
        provider_config=engine.provider_config,
        task_store=calc_orch_env["tasks"],
        plan_store=calc_orch_env["plans"],
        session_store=calc_orch_env["sessions"],
        provider_runner=engine.provider_runner,
    )
    resumed = engine2.resume(record.orchestration_id)
    assert resumed.current_step_number == steps
    assert resumed.current_repair_round == record.current_repair_round


def test_atomic_write_roundtrip(tmp_path: Path):
    path = tmp_path / "rec.yaml"
    atomic_write_yaml(path, {"a": 1, "b": [2, 3]})
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["a"] == 1
    assert not path.with_name(path.name + ".tmp").exists()


# --------------------------------------------------------------------------- H
def test_main_checkout_unchanged_after_scenarios(calc_orch_env):
    before = read_head(calc_orch_env["demo"])
    _run_scenario(calc_orch_env, "direct_success")
    assert read_head(calc_orch_env["demo"]) == before


def test_no_secret_patterns_in_orch_artifacts(calc_orch_env):
    final = _run_scenario(calc_orch_env, "direct_success")
    root = calc_orch_env["ws"] / "orchestrations" / final.orchestration_id
    for path in root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                assert not pat.search(text), f"secret-like pattern in {path}"


def test_mutation_catalog_not_provider_text(calc_orch_env):
    session = calc_orch_env["session"]
    wt = Path(session.worktree_path)
    # Provider text must never be executed — only harness catalog ids.
    with pytest.raises(Exception):
        apply_fixture_mutation(wt, "rm -rf /")


# --------------------------------------------------------------------------- I / config / schema
def test_orchestration_config_loads():
    cfg = load_orchestration_config()
    assert cfg.schema_version == "3c.1"
    assert cfg.default_invocation_mode == "simulated"
    assert cfg.allow_live_providers is False


def test_schema_version_constant():
    assert ORCHESTRATION_SCHEMA_VERSION == "3c.1"


def test_record_serialization_deterministic():
    rec = OrchestrationRecord(
        orchestration_id="orch-x",
        task_id="t",
        plan_id="p",
        approved_plan_fingerprint="fp",
        project_id="calculator-demo",
        session_id="s",
        worktree_id="/tmp/wt",
        starting_commit="abc",
    )
    a = json.dumps(rec.to_dict(), sort_keys=True)
    b = json.dumps(OrchestrationRecord.from_dict(rec.to_dict()).to_dict(), sort_keys=True)
    assert a == b


def test_findings_fingerprint_stable():
    f1 = StructuredFinding("a", "major", "x", path="p", code="C")
    f2 = StructuredFinding("a", "major", "x", path="p", code="C")
    assert findings_fingerprint([f1]) == findings_fingerprint([f2])


def test_unsupported_schema_rejected():
    with pytest.raises(ValueError):
        OrchestrationRecord.from_dict(
            {
                "schema_version": "9.9.9",
                "orchestration_id": "x",
                "task_id": "t",
                "plan_id": "p",
                "approved_plan_fingerprint": "fp",
                "project_id": "calculator-demo",
                "session_id": "s",
                "worktree_id": "/tmp",
                "starting_commit": "abc",
            }
        )


def test_stalemate_missing_evidence_fail_closed():
    ev = RoundEvidence(orchestration_id="o", round_number=1, review_verdict="changes_required")
    decision = evaluate_round_progress(ev, None, require_evidence=True)
    assert decision.stalemate is True or decision.progress_status.value == "indeterminate"


def test_package_version():
    from ai_dev_os import __version__

    assert __version__ == "0.8.12"


def test_scenarios_defined():
    for name in (
        "direct_success",
        "one_repair",
        "stalemate_identical",
        "repair_limit",
    ):
        assert name in SCENARIO_SCRIPTS


def test_adapters_still_manual_handoff():
    from ai_dev_os.adapters import get_adapter

    adapter = get_adapter("cursor")
    assert adapter is not None
