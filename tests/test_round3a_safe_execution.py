"""Round 3A: safe sessions, worktrees, allowlisted execution, audits."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_dev_os.execution_audit import ExecutionAuditStore, serialize_envelope
from ai_dev_os.execution_models import ExecutionStatus, PolicyDecision, SessionStatus
from ai_dev_os.models import ProjectRecord
from ai_dev_os.project_registry import ProjectRegistry, ProjectRegistryError
from ai_dev_os.safe_exec import run_allowlisted
from ai_dev_os.safe_policy import (
    PolicyError,
    assert_executable_allowed,
    assert_no_shell_metacharacters,
    assert_path_confined,
    filter_environment,
)
from ai_dev_os.session_exec import run_session_tests
from ai_dev_os.session_store import SessionError, SessionStore
from ai_dev_os.worktrees import read_head


def _git_init_calculator(path: Path) -> str:
    """Synthetic calculator-demo shaped git repo (not Equitify)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "calculator").mkdir()
    (path / "tests").mkdir()
    (path / "calculator" / "__init__.py").write_text("", encoding="utf-8")
    (path / "calculator" / "ops.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (path / "tests" / "test_ops.py").write_text(
        "from calculator.ops import add, subtract\n"
        "def test_add():\n    assert add(2, 3) == 5\n"
        "def test_subtract():\n    assert subtract(5, 2) == 3\n",
        encoding="utf-8",
    )
    (path / "pyproject.toml").write_text(
        '[project]\nname = "calculator-demo"\nversion = "0.1.0"\n',
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


@pytest.fixture
def calc_env(tmp_path: Path):
    demo = tmp_path / "calculator-demo"
    head = _git_init_calculator(demo)
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(
        ProjectRecord(
            id="calculator-demo",
            name="Calculator Demo",
            root_path=str(demo),
        )
    )
    ws = tmp_path / "workspace"
    store = SessionStore(workspace_root=ws, registry=registry)
    audits = ExecutionAuditStore(workspace_root=ws)
    return {
        "demo": demo,
        "head": head,
        "registry": registry,
        "store": store,
        "audits": audits,
        "ws": ws,
    }


def test_unregistered_project_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    store = SessionStore(workspace_root=tmp_path / "ws", registry=registry)
    with pytest.raises(SessionError, match="Unregistered"):
        store.create(project_id="missing")


def test_equitify_name_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    with pytest.raises(ProjectRegistryError, match="Equitify"):
        registry.register(
            ProjectRecord(
                id="equitify-machine",
                name="Nope",
                root_path=str(tmp_path / "synthetic"),
            )
        )


def test_equitify_path_blob_rejected_on_session():
    from ai_dev_os.safe_policy import assert_not_equitify_blob

    with pytest.raises(PolicyError, match="Equitify"):
        assert_not_equitify_blob(r"C:\Users\Taha\equitify-machine\src")


def test_path_traversal_rejected(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    worktree = Path(session.worktree_path)
    outside = worktree / ".." / ".." / ".." / "escape.txt"
    with pytest.raises(PolicyError, match="escape"):
        assert_path_confined(outside, worktree)


def test_symlink_escape_rejected(calc_env, tmp_path: Path):
    session = calc_env["store"].create(project_id="calculator-demo")
    worktree = Path(session.worktree_path)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("nope", encoding="utf-8")
    link = worktree / "escape-link"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment")
    with pytest.raises(PolicyError, match="escape"):
        assert_path_confined(link / "secret.txt", worktree)


def test_unsupported_executable_rejected():
    with pytest.raises(PolicyError, match="Unsupported executable"):
        assert_executable_allowed("powershell")
    with pytest.raises(PolicyError, match="Unsupported executable"):
        assert_executable_allowed("claude")
    with pytest.raises(PolicyError, match="Unsupported executable"):
        assert_executable_allowed("codex")


def test_shell_operators_rejected():
    with pytest.raises(PolicyError, match="metacharacters"):
        assert_no_shell_metacharacters(["tests", "foo;rm"])
    with pytest.raises(PolicyError, match="metacharacters"):
        assert_no_shell_metacharacters(["a|b"])


def test_timeout_enforcement(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    worktree = Path(session.worktree_path)
    argv = [sys.executable, "-c", "import time; time.sleep(5)"]
    # Direct run_allowlisted still checks executable allowlist; -c is not pytest
    # but python is allowed — Round 3A session_exec only builds pytest argv.
    # For timeout proof use allowlisted python with a sleeper via pytest hang:
    hang = worktree / "tests" / "test_hang.py"
    hang.write_text(
        "import time\ndef test_hang():\n    time.sleep(10)\n",
        encoding="utf-8",
    )
    envelope = run_session_tests(
        session.session_id,
        test_paths=["tests/test_hang.py"],
        timeout=1.0,
        session_store=calc_env["store"],
        audit_store=calc_env["audits"],
    )
    assert envelope.timeout_status is True
    assert envelope.execution_status is ExecutionStatus.TIMEOUT
    assert envelope.policy_decision is PolicyDecision.ALLOW


def test_output_limits():
    from ai_dev_os.safe_exec import _truncate

    text, truncated = _truncate("Y" * 5000, 100)
    assert truncated is True
    assert len(text.encode("utf-8")) < 5000
    assert "[truncated]" in text
    small, small_trunc = _truncate("ok", 100)
    assert small_trunc is False
    assert small == "ok"


def test_safe_exec_refuses_python_c(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    worktree = Path(session.worktree_path)
    envelope = run_allowlisted(
        [sys.executable, "-c", "print(123)"],
        working_directory=worktree,
        confinement_root=worktree,
        session_id=session.session_id,
        project_id=session.project_id,
        starting_commit=session.starting_commit,
    )
    assert envelope.policy_decision is PolicyDecision.DENY
    assert "pytest" in (envelope.rejection_reason or "").lower()


def test_env_secrets_not_inherited(calc_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-should-not-leak")
    monkeypatch.setenv("MY_TOKEN", "tok")
    filtered = filter_environment()
    assert "OPENAI_API_KEY" not in filtered
    assert "MY_TOKEN" not in filtered
    assert "PATH" in filtered

    session = calc_env["store"].create(project_id="calculator-demo")
    worktree = Path(session.worktree_path)
    probe = worktree / "tests" / "test_env_probe.py"
    probe.write_text(
        "import os\n"
        "def test_no_secret():\n"
        "    assert 'OPENAI_API_KEY' not in os.environ\n"
        "    assert 'MY_TOKEN' not in os.environ\n",
        encoding="utf-8",
    )
    envelope = run_session_tests(
        session.session_id,
        test_paths=["tests/test_env_probe.py"],
        session_store=calc_env["store"],
        audit_store=calc_env["audits"],
    )
    assert envelope.execution_status is ExecutionStatus.SUCCESS
    assert envelope.exit_code == 0


def test_targeted_pytest_runs(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    envelope = run_session_tests(
        session.session_id,
        test_paths=["tests/test_ops.py"],
        session_store=calc_env["store"],
        audit_store=calc_env["audits"],
    )
    assert envelope.policy_decision is PolicyDecision.ALLOW
    assert envelope.execution_status is ExecutionStatus.SUCCESS
    assert envelope.exit_code == 0
    assert envelope.tests_requested == ["tests/test_ops.py"]
    assert envelope.automation_status == "local_allowlisted_execution"
    assert envelope.starting_commit == calc_env["head"]
    loaded = calc_env["audits"].load(envelope.execution_id)
    assert loaded.execution_id == envelope.execution_id


def test_deterministic_serialization(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    envelope = run_session_tests(
        session.session_id,
        test_paths=["tests/test_ops.py"],
        session_store=calc_env["store"],
        audit_store=calc_env["audits"],
    )
    text1 = serialize_envelope(envelope)
    text2 = serialize_envelope(envelope)
    assert text1 == text2
    parsed = json.loads(text1)
    assert list(parsed.keys()) == sorted(parsed.keys())
    assert parsed["schema_version"] == "3a.1"


def test_session_identity_immutable(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    with pytest.raises(SessionError, match="project_id"):
        calc_env["store"].assert_immutable_identity(
            session, project_id="other-project"
        )
    with pytest.raises(SessionError, match="starting_commit"):
        calc_env["store"].assert_immutable_identity(
            session, starting_commit="0" * 40
        )
    with pytest.raises(SessionError, match="Cannot mutate"):
        calc_env["store"].update_metadata(
            session.session_id, {"project_id": "hijack"}
        )


def test_cleanup_preserves_main_checkout(calc_env):
    demo = calc_env["demo"]
    head_before = read_head(demo)
    status_before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=demo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    session = calc_env["store"].create(project_id="calculator-demo")
    worktree = Path(session.worktree_path)
    assert worktree.exists()
    cleaned = calc_env["store"].cleanup(session.session_id)
    assert cleaned.status is SessionStatus.CLEANED_UP
    assert not worktree.exists()
    assert read_head(demo) == head_before
    status_after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=demo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert status_after == status_before


def test_run_tests_rejects_cleaned_session(calc_env):
    session = calc_env["store"].create(project_id="calculator-demo")
    calc_env["store"].cleanup(session.session_id)
    envelope = run_session_tests(
        session.session_id,
        test_paths=["tests/test_ops.py"],
        session_store=calc_env["store"],
        audit_store=calc_env["audits"],
    )
    assert envelope.execution_status is ExecutionStatus.REJECTED
    assert envelope.policy_decision is PolicyDecision.DENY


def test_session_exec_rejects_path_escape(calc_env, tmp_path: Path):
    session = calc_env["store"].create(project_id="calculator-demo")
    envelope = run_session_tests(
        session.session_id,
        test_paths=["../../../outside"],
        session_store=calc_env["store"],
        audit_store=calc_env["audits"],
    )
    assert envelope.policy_decision is PolicyDecision.DENY
    assert "escape" in (envelope.rejection_reason or "").lower()
