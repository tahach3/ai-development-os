"""Round 4F: CI ergonomics — flaky isolation, coverage notes, workflow wiring."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from unittest import mock

import pytest
import yaml

from ai_dev_os import __version__
from ai_dev_os.ci_config import load_ci_policy
from ai_dev_os.ci_engine import exit_code_for_run, run_ci_check
from ai_dev_os.ci_models import CIFailureClass, CIVerdict, STAGE_ORDER
from ai_dev_os.ci_pytest_ergonomics import parse_failed_nodeids
from ai_dev_os.ci_stages import stage_pytest_suite
from ai_dev_os.cli import build_parser


REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    return completed.stdout


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "ci@example.com")
    _git(root, "config", "user.name", "CI")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "init")


def _write_pytest_repo(root: Path, test_body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True)
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "workspace").mkdir(parents=True)
    (root / "src" / "pkg" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (root / "tests" / "test_sample.py").write_text(test_body, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "temp-4f"
            version = "0.0.1"
            requires-python = ">=3.11"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    policy_src = REPO_ROOT / "config" / "ci_policy.yaml"
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "ci_policy.yaml").write_text(
        policy_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _init_repo(root)
    return root


FLAKY_BODY = textwrap.dedent(
    """
    from pathlib import Path

    MARKER = Path("workspace") / "_flaky_once_marker"

    def test_flaky_once():
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        if not MARKER.exists():
            MARKER.write_text("1", encoding="utf-8")
            assert False, "intentional first-run failure"
        assert True
    """
).strip() + "\n"

ALWAYS_FAIL_BODY = "def test_always_fail():\n    assert False, 'genuine failure'\n"


def test_parse_failed_nodeids():
    text = (
        "FAILED tests/test_sample.py::test_flaky_once - AssertionError\n"
        "ERROR tests/test_other.py::test_x - boom\n"
        "some other line\n"
    )
    assert parse_failed_nodeids(text) == [
        "tests/test_sample.py::test_flaky_once",
        "tests/test_other.py::test_x",
    ]


def test_isolate_flaky_detects_fail_then_pass(tmp_path: Path):
    repo = _write_pytest_repo(tmp_path / "flaky", FLAKY_BODY)
    policy = load_ci_policy(repo / "config" / "ci_policy.yaml")
    stage, _counts = stage_pytest_suite(repo, policy, isolate_flaky=True)
    assert stage.validation_status == "passed"
    assert stage.failure_class == CIFailureClass.FLAKY_TEST_DETECTED.value
    assert stage.blocker is False
    assert any("FLAKY TEST DETECTED" in n for n in stage.notes)
    assert any("flaky_node:" in n for n in stage.notes)
    assert any("test_flaky_once" in n for n in stage.notes)


def test_isolate_flaky_genuine_fail_stays_failed(tmp_path: Path):
    repo = _write_pytest_repo(tmp_path / "fail", ALWAYS_FAIL_BODY)
    policy = load_ci_policy(repo / "config" / "ci_policy.yaml")
    stage, _counts = stage_pytest_suite(repo, policy, isolate_flaky=True)
    assert stage.validation_status == "failed"
    assert stage.failure_class == CIFailureClass.TESTS_FAILED.value
    assert stage.blocker is True


def test_default_no_isolate_flag_unchanged_fail(tmp_path: Path):
    repo = _write_pytest_repo(tmp_path / "default", ALWAYS_FAIL_BODY)
    policy = load_ci_policy(repo / "config" / "ci_policy.yaml")
    stage, _counts = stage_pytest_suite(repo, policy)
    assert stage.validation_status == "failed"
    assert stage.failure_class == CIFailureClass.TESTS_FAILED.value
    assert stage.blocker is True
    assert not any("FLAKY" in n for n in stage.notes)


def test_isolate_flaky_pass_with_notes_verdict(tmp_path: Path):
    repo = _write_pytest_repo(tmp_path / "verdict", FLAKY_BODY)
    # Minimal ci-check: only pytest_suite
    run = run_ci_check(
        repo,
        only_stages=["pytest_suite"],
        isolate_flaky=True,
        persist=False,
    )
    assert run.final_verdict == CIVerdict.PASS_WITH_NOTES.value
    assert CIFailureClass.FLAKY_TEST_DETECTED.value in run.failure_classes
    assert exit_code_for_run(run) == 0


def test_coverage_present_non_blocking_note(tmp_path: Path):
    pytest.importorskip("coverage")
    repo = _write_pytest_repo(
        tmp_path / "cov_ok",
        "def test_ok():\n    assert True\n",
    )
    policy = load_ci_policy(repo / "config" / "ci_policy.yaml")
    stage, _ = stage_pytest_suite(repo, policy, coverage=True)
    assert stage.validation_status == "passed"
    assert stage.blocker is False
    assert any("coverage total:" in n for n in stage.notes)
    assert stage.failure_class in {
        CIFailureClass.NONE.value,
        CIFailureClass.FLAKY_TEST_DETECTED.value,
    }


def test_coverage_absent_graceful_note(tmp_path: Path):
    repo = _write_pytest_repo(
        tmp_path / "cov_missing",
        "def test_ok():\n    assert True\n",
    )
    policy = load_ci_policy(repo / "config" / "ci_policy.yaml")
    with mock.patch(
        "ai_dev_os.ci_pytest_ergonomics.coverage_module_available",
        return_value=False,
    ):
        stage, _ = stage_pytest_suite(repo, policy, coverage=True)
    assert stage.validation_status == "passed"
    assert any(
        "coverage not measured (install optional extra)" in n for n in stage.notes
    )
    assert stage.blocker is False


def test_coverage_does_not_affect_fail_verdict(tmp_path: Path):
    pytest.importorskip("coverage")
    repo = _write_pytest_repo(tmp_path / "cov_fail", ALWAYS_FAIL_BODY)
    policy = load_ci_policy(repo / "config" / "ci_policy.yaml")
    stage, _ = stage_pytest_suite(repo, policy, coverage=True)
    assert stage.validation_status == "failed"
    assert stage.failure_class == CIFailureClass.TESTS_FAILED.value
    assert stage.blocker is True


def test_workflow_permissions_and_steps():
    path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["permissions"] == {"contents": "read"}
    text = path.read_text(encoding="utf-8")
    code = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "${{ secrets." not in code
    assert "secrets." not in code
    steps = data["jobs"]["local-ci"]["steps"]
    run_cmds = [s.get("run", "") for s in steps if isinstance(s, dict)]
    assert any("pytest -q" in c for c in run_cmds)
    assert any("ci-check" in c for c in run_cmds)
    assert any("ci-targeted" in c for c in run_cmds)
    targeted = [s for s in steps if "ci-targeted" in str(s.get("run", ""))]
    assert targeted
    assert targeted[0].get("if") == "github.event_name == 'pull_request'"


def test_cli_flags_registered():
    parser = build_parser()
    args = parser.parse_args(["ci-check", "--isolate-flaky", "--coverage"])
    assert args.isolate_flaky is True
    assert args.coverage is True
    targs = parser.parse_args(["ci-targeted", "--base", "abc123", "--isolate-flaky"])
    assert targs.base == "abc123"
    assert targs.isolate_flaky is True


def test_stage_order_unchanged():
    assert "project_boundaries" not in STAGE_ORDER
    assert STAGE_ORDER[0] == "repo_identity"
    assert STAGE_ORDER[-1] == "finalize"
    assert "pytest_suite" in STAGE_ORDER


def test_version_is_0_8_7():
    assert __version__ == "0.8.11"


def test_optional_cov_extra_declared():
    # pyproject must declare cov optional; never a runtime dep
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'cov = [' in text or 'cov =' in text
    assert "coverage>=" in text
    # runtime dependencies block must not require coverage
    before_opt = text.split("[project.optional-dependencies]")[0]
    assert "coverage" not in before_opt
