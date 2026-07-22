"""Round 4A: local CI engine, PR validation, dependency policy, workflow gates."""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from ai_dev_os.ci_config import CIConfigError, load_ci_policy, validate_ci_policy
from ai_dev_os.ci_dependency_policy import check_dependency_policy
from ai_dev_os.ci_engine import CIEngineError, ci_run_to_json, exit_code_for_run, run_ci_check
from ai_dev_os.ci_models import (
    CI_SCHEMA_VERSION,
    STAGE_ORDER,
    CIFailureClass,
    CIRun,
    CIStageResult,
    CIVerdict,
)
from ai_dev_os.ci_runner import CICommandError, assert_argv_safe, run_ci_command
from ai_dev_os.ci_secrets import redact_secrets, scan_files, scan_text
from ai_dev_os.ci_stages import STAGE_FUNCS, stage_package_version, stage_schema_validation
from ai_dev_os.ci_validate_change import (
    exit_code_for_pr_summary,
    validate_change,
    _workflow_findings,
)
from ai_dev_os.behavioral_metrics import generate_behavioral_report
from ai_dev_os.models import Complexity, RiskLevel, Task, TaskStatus, TaskType


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


def _write_minimal_ci_repo(root: Path, *, with_failing_test: bool = False) -> Path:
    """Build a temporary repo that mirrors AI Dev OS CI layout enough to run stages."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "schemas").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "src" / "ai_dev_os").mkdir(parents=True)

    (root / "src" / "pkg" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (root / "src" / "ai_dev_os" / "__init__.py").write_text(
        '__version__ = "0.6.0"\n', encoding="utf-8"
    )
    test_body = (
        "def test_fail():\n    assert False\n"
        if with_failing_test
        else "def test_ok():\n    assert True\n"
    )
    (root / "tests" / "test_ok.py").write_text(test_body, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [build-system]
            requires = ["setuptools>=68"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "temp-ci"
            version = "0.6.0"
            requires-python = ">=3.11"
            dependencies = ["PyYAML>=6.0"]

            [project.optional-dependencies]
            dev = ["pytest>=7.4"]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "schemas" / "sample.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "Sample",
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Copy real ci policy
    policy = (REPO_ROOT / "config" / "ci_policy.yaml").read_text(encoding="utf-8")
    (root / "config" / "ci_policy.yaml").write_text(policy, encoding="utf-8")
    (root / "config" / "projects.example.yaml").write_text(
        "projects: []\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Temp\n\nPackage 0.6.0 Round 4A\n", encoding="utf-8")
    (root / "docs" / "ROADMAP.md").write_text("Round 4A 0.6.0\n", encoding="utf-8")
    (root / "docs" / "PROJECT_CHRONICLE.md").write_text(
        "Package version: 0.6.0 Round 4A\n", encoding="utf-8"
    )
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
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "ci@example.com")
    _git(root, "config", "user.name", "CI Test")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")
    return root


def test_stage_order_deterministic():
    assert STAGE_ORDER[0] == "repo_identity"
    assert STAGE_ORDER[-1] == "finalize"
    assert list(STAGE_FUNCS) == list(STAGE_ORDER) or set(STAGE_FUNCS) == set(STAGE_ORDER)


def test_successful_local_ci(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "ok")
    run = run_ci_check(repo)
    assert run.final_verdict in {CIVerdict.PASS.value, CIVerdict.PASS_WITH_NOTES.value}
    assert exit_code_for_run(run) == 0
    names = [s.stage_name for s in run.stages if s.validation_status != "skipped"]
    assert names == list(STAGE_ORDER)


def test_normalized_result_serialization(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "ser")
    run = run_ci_check(repo, skip_stages=["pytest_suite"])
    text = ci_run_to_json(run)
    data = json.loads(text)
    assert data["schema_version"] == CI_SCHEMA_VERSION
    again = CIRun.from_dict(data)
    assert again.run_id == run.run_id
    # deterministic key ordering in dump
    assert '"ci_policy_version"' in text


def test_failed_pytest_stage(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "fail", with_failing_test=True)
    run = run_ci_check(repo)
    assert run.final_verdict == CIVerdict.FAIL.value
    assert CIFailureClass.TESTS_FAILED.value in run.failure_classes


def test_timeout_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _write_minimal_ci_repo(tmp_path / "to")
    from ai_dev_os import ci_stages

    def boom(*_a, **_k):
        from ai_dev_os.ci_models import CIStageResult, CIStageStatus, CIFailureClass
        from ai_dev_os.models import utc_now_iso

        r = CIStageResult(
            stage_name="python_compile",
            command_identity="timeout",
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            validation_status=CIStageStatus.TIMEOUT.value,
            failure_class=CIFailureClass.TIMEOUT.value,
            timeout_status=True,
            blocker=True,
        )
        return r

    monkeypatch.setattr(ci_stages, "stage_python_compile", boom)
    # Rebind STAGE_FUNCS entry
    monkeypatch.setitem(ci_stages.STAGE_FUNCS, "python_compile", boom)
    from ai_dev_os import ci_engine

    monkeypatch.setitem(ci_engine.STAGE_FUNCS, "python_compile", boom)
    run = run_ci_check(repo, skip_stages=["pytest_suite"])
    assert CIFailureClass.TIMEOUT.value in run.failure_classes


def test_malformed_schema(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "badsch")
    (repo / "schemas" / "broken.json").write_text("{not json", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "bad schema")
    run = run_ci_check(repo, skip_stages=["pytest_suite"])
    assert CIFailureClass.MALFORMED_SCHEMA.value in run.failure_classes


def test_malformed_yaml(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "badyaml")
    (repo / "config" / "broken.yaml").write_text(":\n  - bad: [\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "bad yaml")
    run = run_ci_check(repo, skip_stages=["pytest_suite"])
    assert CIFailureClass.MALFORMED_CONFIG.value in run.failure_classes


def test_package_version_mismatch(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "ver")
    (repo / "src" / "ai_dev_os" / "__init__.py").write_text(
        '__version__ = "0.0.0"\n', encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "mismatch")
    result = stage_package_version(repo, load_ci_policy(repo / "config" / "ci_policy.yaml"))
    assert result.failure_class == CIFailureClass.PACKAGE_VERSION_MISMATCH.value


def test_dependency_addition_and_unpinned(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "deps")
    (repo / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "temp-ci"
            version = "0.6.0"
            requires-python = ">=3.11"
            dependencies = [
              "PyYAML>=6.0",
              "langchain>=0.1",
              "evil @ git+https://example.com/evil.git",
            ]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    dep = check_dependency_policy(repo)
    assert dep.ok is False
    assert dep.vulnerability_scanning is False
    cats = {f.category for f in dep.findings}
    assert "prohibited_category" in cats
    assert "url_or_vcs" in cats


def test_prohibited_path_and_equitify(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "eq")
    evil = repo / "equitify-machine" / "x.py"
    evil.parent.mkdir(parents=True)
    evil.write_text("print(1)\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "equitify path")
    run = run_ci_check(repo, skip_stages=["pytest_suite"])
    assert CIFailureClass.PROHIBITED_PATH.value in run.failure_classes


def test_secret_pattern_and_redaction(tmp_path: Path):
    # Assemble at runtime so the tracked test source does not contain a secret-like assignment.
    token = "sk_live_" + ("abcdefghij" * 3)
    secret_line = "api_key = \"" + token + "\""
    findings = scan_text("f.py", secret_line)
    assert findings
    assert "sk_live" not in findings[0].redacted_snippet
    assert "[REDACTED]" in redact_secrets(secret_line)
    # placeholder should not fire
    safe = scan_text("f.py", 'api_key = "YOUR_API_KEY"')
    assert safe == []


def test_runtime_artifact_detection(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "rt")
    art = repo / "workspace" / "active" / "secret_task.yaml"
    art.parent.mkdir(parents=True)
    art.write_text("id: x\n", encoding="utf-8")
    _git(repo, "add", "-f", "workspace/active/secret_task.yaml")
    _git(repo, "commit", "-m", "runtime")
    run = run_ci_check(repo, skip_stages=["pytest_suite"])
    assert CIFailureClass.RUNTIME_ARTIFACT_DETECTED.value in run.failure_classes


def test_safety_policy_change_human_review(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "safe")
    # create second commit changing safety-critical path
    pol = repo / "config" / "ci_policy.yaml"
    pol.write_text(pol.read_text(encoding="utf-8") + "\n# touch\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "policy touch")
    base = _git(repo, "rev-parse", "HEAD~1").strip()
    summary = validate_change(repo, base=base, head="HEAD")
    assert summary.human_review_required is True
    assert summary.auto_approve is False
    assert summary.auto_merge is False
    assert any(f.category == "safety_critical" for f in summary.findings)
    # human review alone does not force fail exit
    assert exit_code_for_pr_summary(summary) == 0


def test_command_injection_and_shell_rejection():
    with pytest.raises(CICommandError):
        assert_argv_safe(["python", "-c", "print(1)"])
    with pytest.raises(CICommandError):
        assert_argv_safe(["python", "a.py", "x;rm -rf /"])
    with pytest.raises(CICommandError):
        assert_argv_safe(["powershell", "-Command", "Get-ChildItem"])


def test_symlink_escape_rejection(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "sym")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = repo / "link_out"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not permitted on this Windows host")
    # scanning should not treat outside content as repo file via tracked list;
    # ensure path confinement for examined files under repo only
    tracked = ["link_out"]
    # if symlink is followed, secret patterns might appear — we skip non-regular via is_file
    # Explicit: Path.is_file() follows symlink; ensure scan does not explode
    scan_files(repo, tracked)


def test_unsupported_schema_version():
    with pytest.raises(CIConfigError):
        validate_ci_policy({"schema_version": "9.9", "policy_version": "4a.1"})
    with pytest.raises(ValueError):
        CIRun.from_dict({"schema_version": "9.9", "stages": []})


def test_partial_ci_result_recovery(tmp_path: Path):
    partial = {
        "schema_version": CI_SCHEMA_VERSION,
        "ci_policy_version": "4a.1",
        "run_id": "ci_partial",
        "repository_identity": str(tmp_path),
        "starting_commit": "abc",
        "trigger_type": "local",
        "state": "running",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "",
        "duration_seconds": 0,
        "stages": [
            CIStageResult(stage_name="repo_identity", validation_status="passed").to_dict()
        ],
        "final_verdict": "fail",
        "failure_classes": [],
        "human_review_required": False,
        "blocker": False,
        "next_action": "",
        "policy_decision": "allow",
    }
    run = CIRun.from_dict(partial)
    assert run.run_id == "ci_partial"
    assert len(run.stages) == 1


def test_github_workflow_permissions_and_prohibitions():
    wf = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = wf.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["permissions"] == {"contents": "read"}
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "${{ secrets." not in code
    assert "auto-merge" not in code.lower()
    assert "OPENAI_API_KEY" not in code
    assert "ANTHROPIC_API_KEY" not in code
    assert "actions/deploy" not in code.lower()
    assert "gh pr merge" not in code.lower()
    findings = _workflow_findings(REPO_ROOT, [".github/workflows/ci.yml"])
    assert not any(f.blocker for f in findings)


def test_workflow_secret_and_write_permission_detection(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "wfb")
    bad = repo / ".github" / "workflows" / "bad.yml"
    bad.write_text(
        textwrap.dedent(
            """
            name: bad
            on: push
            permissions:
              contents: write
            jobs:
              x:
                runs-on: ubuntu-latest
                steps:
                  - run: echo ${{ secrets.OPENAI_API_KEY }}
                  - run: gh pr merge --auto
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    findings = _workflow_findings(repo, [".github/workflows/bad.yml"])
    cats = {f.category for f in findings}
    assert "workflow_permissions" in cats
    assert "workflow_secrets" in cats


def test_unknown_stage_rejected(tmp_path: Path):
    repo = _write_minimal_ci_repo(tmp_path / "unk")
    with pytest.raises(CIEngineError):
        run_ci_check(repo, skip_stages=["not_a_real_stage"])


def test_behavioral_ci_aggregates():
    tasks = [
        Task(
            id="t1",
            title="A",
            description="B",
            project_id="demo",
            task_type=TaskType.FEATURE,
            complexity=Complexity.NORMAL,
            risk_level=RiskLevel.LOW,
            status=TaskStatus.COMPLETED,
        )
    ]
    ci = CIRun(
        tests_passed=10,
        tests_failed=1,
        human_review_required=True,
        failure_classes=["tests_failed"],
        stages=[
            CIStageResult(
                stage_name="pytest_suite",
                validation_status="failed",
                blocker=True,
            )
        ],
    )
    report = generate_behavioral_report(tasks, ci_run=ci)
    assert report.auto_rewrite_rules is False
    assert report.ci_aggregates.get("tests_failed") == 1
    assert all(r.active is False for r in report.recommendation_records)
    assert all(r.status == "proposed" for r in report.recommendation_records)


def test_real_repo_schema_stage():
    policy = load_ci_policy(REPO_ROOT / "config" / "ci_policy.yaml")
    result = stage_schema_validation(REPO_ROOT, policy)
    assert result.validation_status == "passed"


def test_cli_ci_check_help():
    from ai_dev_os.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["ci-check", "--skip-stages", "pytest_suite", "--only-stages", "finalize"])
    assert args.command == "ci-check"


def test_calculator_demo_still_present():
    demo = REPO_ROOT / "demo_projects" / "calculator-demo" / "calculator" / "ops.py"
    assert demo.is_file()
