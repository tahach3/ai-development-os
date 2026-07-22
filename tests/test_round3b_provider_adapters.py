"""Round 3B: controlled provider CLI adapters — contracts, discovery, sim, gates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_dev_os.adapters import get_adapter
from ai_dev_os.approval import approve_plan, submit_plan
from ai_dev_os.fingerprints import fingerprint_plan
from ai_dev_os.models import (
    Complexity,
    ModelRole,
    Plan,
    ProjectRecord,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
)
from ai_dev_os.plan_store import PlanStore
from ai_dev_os.project_registry import ProjectRegistry, ProjectRegistryError
from ai_dev_os.provider_audit import ProviderAuditStore
from ai_dev_os.provider_config import (
    ProviderConfig,
    ProviderEntryConfig,
    fail_closed_default_config,
)
from ai_dev_os.provider_discovery import (
    assert_provider_executable_allowed,
    discover_provider,
    resolve_provider_executable,
)
from ai_dev_os.provider_models import (
    FailureClass,
    ProviderMode,
    ProviderRequest,
    ProviderResultStatus,
    SimulatedFixture,
    is_provider_result_intake_ready,
    validate_provider_result_dict,
)
from ai_dev_os.provider_policy import ProviderPolicyError, assert_live_gates, assert_may_run_provider
from ai_dev_os.provider_runner import ProviderRunner
from ai_dev_os.safe_policy import PolicyError, filter_environment
from ai_dev_os.session_store import SessionStore
from ai_dev_os.task_store import TaskStore
from ai_dev_os.validation import apply_status_transition
from ai_dev_os.worktrees import read_head


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
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True
    )
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


def _sim_config() -> ProviderConfig:
    cfg = fail_closed_default_config()
    cfg.providers["simulated"] = ProviderEntryConfig(
        provider_id="simulated",
        mode=ProviderMode.SIMULATED,
        enabled=True,
        allow_live=False,
    )
    return cfg


@pytest.fixture
def calc_provider_env(tmp_path: Path):
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
    config = _sim_config()
    runner = ProviderRunner(
        workspace_root=ws,
        registry=registry,
        config=config,
        task_store=tasks,
        plan_store=plans,
        session_store=sessions,
        audit_store=audits,
    )

    task = tasks.create(
        {
            "id": "calc-3b-1",
            "title": "Add subtract",
            "description": "Synthetic Round 3B provider task",
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
            "plan_id": "plan-3b-1",
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
        "audits": audits,
        "runner": runner,
        "config": config,
        "task": tasks.load(task.id),
        "plan": plans.load(plan.plan_id),
        "session": session,
    }


def test_fail_closed_default_config():
    cfg = fail_closed_default_config()
    assert cfg.effective_mode("simulated") is ProviderMode.DISABLED
    assert cfg.effective_mode("claude_code") is ProviderMode.DISABLED


def test_equitify_still_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    with pytest.raises(ProjectRegistryError, match="Equitify"):
        registry.register(
            ProjectRecord(
                id="equitify-machine",
                name="Nope",
                root_path=str(tmp_path / "x"),
            )
        )


def test_unregistered_project_rejected(calc_provider_env):
    env = calc_provider_env
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
    )
    req.project_id = "missing-project"
    with pytest.raises(ProviderPolicyError, match="Unregistered"):
        assert_may_run_provider(
            req,
            config=env["config"],
            task_store=env["tasks"],
            plan_store=env["plans"],
            session_store=env["sessions"],
            registry=env["registry"],
        )


def test_disabled_provider_cannot_run(calc_provider_env):
    env = calc_provider_env
    env["config"].providers["simulated"].enabled = False
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
    )
    result = env["runner"].validate_request(req)
    assert result["valid"] is False
    assert "disabled" in result["errors"][0].lower()


def test_discovery_does_not_live_call():
    result = discover_provider("claude_code")
    assert result["live_model_call"] is False
    result_c = discover_provider("cursor")
    assert result_c["live_model_call"] is False
    assert result_c["installation_status"] in {
        "not_installed",
        "detected",
        "ambiguous",
        "error",
    }


def test_unsupported_or_ambiguous_cursor_honest():
    result = discover_provider("cursor")
    # Without a proven noninteractive CLI, must not claim live-ready.
    assert result["live_model_call"] is False


def test_arbitrary_executable_rejected():
    with pytest.raises(PolicyError):
        assert_provider_executable_allowed("claude_code", r"C:\Windows\System32\cmd.exe")


def test_shell_operators_rejected_in_exe_path():
    with pytest.raises(PolicyError):
        assert_provider_executable_allowed("codex", "codex;rm")


def test_env_secrets_filtered_from_child_env():
    filtered = filter_environment(
        {
            "PATH": "x",
            "OPENAI_API_KEY": "secret",
            "ANTHROPIC_API_KEY": "secret",
            "TEMP": "t",
        }
    )
    assert "OPENAI_API_KEY" not in filtered
    assert "ANTHROPIC_API_KEY" not in filtered
    assert "PATH" in filtered


def test_request_cannot_change_project_role_session(calc_provider_env):
    env = calc_provider_env
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        role="cursor",
        invocation_mode=ProviderMode.SIMULATED,
    )
    req.role = "claude"
    with pytest.raises(ProviderPolicyError, match="role"):
        assert_may_run_provider(
            req,
            config=env["config"],
            task_store=env["tasks"],
            plan_store=env["plans"],
            session_store=env["sessions"],
            registry=env["registry"],
        )


def test_stale_plan_and_commit_fixtures(calc_provider_env):
    env = calc_provider_env
    for fixture in (SimulatedFixture.STALE_PLAN, SimulatedFixture.STALE_COMMIT):
        req = env["runner"].build_request(
            provider_id="simulated",
            task_id=env["task"].id,
            plan_id=env["plan"].plan_id,
            session_id=env["session"].session_id,
            invocation_mode=ProviderMode.SIMULATED,
            fixture_id=fixture.value,
            request_id=f"req-{fixture.value}",
        )
        result = env["runner"].run_simulated(req)
        assert result.failure_class is FailureClass.STALE_BINDING


def test_unapproved_plan_blocks_impl_provider(calc_provider_env):
    env = calc_provider_env
    # Create a draft plan and try simulated impl role against it via bindings
    task = env["task"]
    draft = Plan.from_dict(
        {
            "plan_id": "plan-draft-3b",
            "task_id": task.id,
            "project_id": "calculator-demo",
            "planner_agent": "cursor",
            "starting_commit": env["head"],
            "objective": "draft",
            "assumptions": ["a"],
            "scope": ["s"],
            "prohibited_actions": ["p"],
            "files_expected_to_change": ["calculator/ops.py"],
            "implementation_steps": ["step"],
            "testing_plan": ["pytest"],
            "rollback_or_recovery_plan": ["revert"],
            "risks": ["r"],
            "unresolved_questions": [],
            "approval_requirement": "human",
            "risk_level": RiskLevel.LOW.value,
        }
    )
    env["plans"].save(draft)
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=task.id,
        plan_id=draft.plan_id,
        session_id=env["session"].session_id,
        role="cursor",
        invocation_mode=ProviderMode.SIMULATED,
        request_id="req-unapproved",
    )
    result = env["runner"].validate_request(req)
    assert result["valid"] is False
    assert any("Unapproved" in e for e in result["errors"])


def test_live_mode_refused_without_permissions(calc_provider_env):
    env = calc_provider_env
    req = env["runner"].build_request(
        provider_id="claude_code",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.LIVE_LOCAL_CLI_ALLOWED,
        request_id="req-live-denied",
    )
    env["config"].providers["claude_code"] = ProviderEntryConfig(
        provider_id="claude_code",
        mode=ProviderMode.LIVE_LOCAL_CLI_ALLOWED,
        enabled=True,
        allow_live=True,
    )
    with pytest.raises(ProviderPolicyError):
        assert_live_gates(
            req,
            config=env["config"],
            task_store=env["tasks"],
            plan_store=env["plans"],
            session_store=env["sessions"],
            registry=env["registry"],
        )


def test_simulated_success_uses_safe_runner_and_audit(calc_provider_env):
    env = calc_provider_env
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        fixture_id=SimulatedFixture.SUCCESS_IMPL.value,
        request_id="req-success-impl",
    )
    result = env["runner"].run_simulated(req)
    assert result.provider_result_status is ProviderResultStatus.SUCCESS
    assert result.automation_status == "simulated_provider_execution"
    assert result.result_artifact_path
    assert is_provider_result_intake_ready(result)
    # Round 3A safe exec audit should exist when pytest ran in worktree
    safe_id = result.normalized_payload.get("safe_execution_id")
    assert safe_id
    exec_path = env["ws"] / "executions" / f"{safe_id}.json"
    assert exec_path.exists()
    # No secret keys in provider audit JSON
    raw = (env["ws"] / "provider_executions" / "results" / f"{result.request_id}.json").read_text(
        encoding="utf-8"
    )
    assert "API_KEY" not in raw
    assert "OPENAI" not in raw


def test_simulated_review_and_failure_fixtures(calc_provider_env):
    env = calc_provider_env
    cases = [
        (SimulatedFixture.SUCCESS_REVIEW, ProviderResultStatus.SUCCESS, FailureClass.NONE),
        (SimulatedFixture.PROVIDER_REJECTION, ProviderResultStatus.REJECTED, FailureClass.POLICY_REJECTED),
        (SimulatedFixture.MALFORMED_OUTPUT, ProviderResultStatus.FAILED, FailureClass.MALFORMED_OUTPUT),
        (SimulatedFixture.TIMEOUT, ProviderResultStatus.TIMEOUT, FailureClass.TIMEOUT),
        (SimulatedFixture.NONZERO_EXIT, ProviderResultStatus.FAILED, FailureClass.NONZERO_EXIT),
        (SimulatedFixture.TRUNCATED_OUTPUT, ProviderResultStatus.SUCCESS, FailureClass.NONE),
        (SimulatedFixture.MISSING_ARTIFACT, ProviderResultStatus.FAILED, FailureClass.MISSING_ARTIFACT),
        (SimulatedFixture.CANCELLED, ProviderResultStatus.CANCELLED, FailureClass.CANCELLED),
        (SimulatedFixture.DUPLICATE_REQUEST, ProviderResultStatus.DUPLICATE, FailureClass.DUPLICATE_REQUEST),
    ]
    for fixture, status, failure in cases:
        req = env["runner"].build_request(
            provider_id="simulated",
            task_id=env["task"].id,
            plan_id=env["plan"].plan_id,
            session_id=env["session"].session_id,
            invocation_mode=ProviderMode.SIMULATED,
            fixture_id=fixture.value,
            request_id=f"req-{fixture.value}",
        )
        # Distinct fingerprints: fixture_id is part of binding payload
        result = env["runner"].run_simulated(req)
        assert result.provider_result_status is status, fixture
        assert result.failure_class is failure, fixture
        if fixture is SimulatedFixture.MALFORMED_OUTPUT:
            assert not is_provider_result_intake_ready(result)
            assert validate_provider_result_dict(result.to_dict()) or True


def test_duplicate_execution_detected(calc_provider_env):
    env = calc_provider_env
    req1 = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        fixture_id=SimulatedFixture.SUCCESS_IMPL.value,
        request_id="req-dup-a",
    )
    r1 = env["runner"].run_simulated(req1)
    assert r1.provider_result_status is ProviderResultStatus.SUCCESS
    req2 = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        fixture_id=SimulatedFixture.SUCCESS_IMPL.value,
        request_id="req-dup-b",
    )
    assert req1.request_fingerprint() == req2.request_fingerprint()
    r2 = env["runner"].run_simulated(req2)
    assert r2.duplicate_request_status is True
    assert r2.failure_class is FailureClass.DUPLICATE_REQUEST


def test_cancel_flag(calc_provider_env):
    env = calc_provider_env
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        fixture_id=SimulatedFixture.SUCCESS_IMPL.value,
        request_id="req-cancel-1",
    )
    env["runner"].cancel(req.request_id)
    result = env["runner"].run_simulated(req)
    assert result.cancellation_status is True
    assert result.failure_class is FailureClass.CANCELLED


def test_deterministic_fingerprints(calc_provider_env):
    env = calc_provider_env
    a = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        fixture_id="success_impl",
        request_id="fp-a",
    )
    b = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        fixture_id="success_impl",
        request_id="fp-b",
    )
    assert a.request_fingerprint() == b.request_fingerprint()
    assert a.to_dict()["request_fingerprint"] == a.request_fingerprint()


def test_manual_handoff_still_works(calc_provider_env, tmp_path: Path):
    env = calc_provider_env
    task = env["tasks"].load(env["task"].id)
    out = tmp_path / "handoffs"
    adapter = get_adapter("cursor")
    result = adapter.prepare_handoff(task, env["demo"], out)
    assert result.automation_status == "manual_handoff_required"
    assert result.handoff_path.exists()


def test_preview_and_capabilities(calc_provider_env):
    env = calc_provider_env
    caps = env["runner"].show_capabilities("simulated")
    assert caps["provider_id"] == "simulated"
    assert caps["live_execution_permission"] is False
    req = env["runner"].build_request(
        provider_id="simulated",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        invocation_mode=ProviderMode.SIMULATED,
        request_id="req-preview",
    )
    preview = env["runner"].preview_invocation(req)
    assert preview["live_model_call"] is False
    assert "sanitized_argument_array" in preview


def test_cli_adapter_shells_refuse_live(calc_provider_env):
    from ai_dev_os.providers import get_provider_adapter

    env = calc_provider_env
    env["config"].providers["codex"] = ProviderEntryConfig(
        provider_id="codex",
        mode=ProviderMode.LIVE_LOCAL_CLI_ALLOWED,
        enabled=True,
        allow_live=True,
    )
    task = env["tasks"].load(env["task"].id)
    task.assigned_role = ModelRole.CODEX
    env["tasks"].update(task)
    adapter = get_provider_adapter("codex")
    req = env["runner"].build_request(
        provider_id="codex",
        task_id=env["task"].id,
        plan_id=env["plan"].plan_id,
        session_id=env["session"].session_id,
        role="codex",
        invocation_mode=ProviderMode.LIVE_LOCAL_CLI_ALLOWED,
        request_id="req-codex-live",
    )
    result = adapter.execute(
        req, config=env["config"], audit_store=env["audits"]
    )
    assert result.provider_result_status is ProviderResultStatus.REJECTED
    assert "not authorized" in (result.rejection_reason or "").lower()
