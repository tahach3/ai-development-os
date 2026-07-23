"""Round 4A hardening tests.

Covers the additive local-CI extensions layered on the existing Round 4A
foundation:

* cross-platform executable-location redaction (privacy / determinism fix)
* deterministic targeted / related-module test selection and execution
* CI run history indexing + regression comparison (audit usability)
* deterministic human-readable CI report rendering
* CLI wiring and backward-compatibility / boundary guarantees
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_dev_os.ci_config import CIPolicy
from ai_dev_os.ci_history import (
    CIRunComparison,
    compare_runs,
    compare_to_previous,
    latest_passing_run,
    list_runs,
    load_run,
)
from ai_dev_os.ci_models import (
    STAGE_ORDER,
    CIRun,
    CIStageResult,
    CIStageStatus,
    CIVerdict,
)
from ai_dev_os.ci_report import (
    render_ci_summary,
    render_comparison,
    render_targeted_summary,
)
from ai_dev_os.ci_test_selection import (
    DEFAULT_BROAD_IMPACT_GLOBS,
    TargetedSelection,
    run_targeted_tests,
    select_related_tests,
)
from ai_dev_os.provider_readiness_discovery import sanitize_executable_location


# --------------------------------------------------------------------------- #
# A. cross-platform sanitize fix
# --------------------------------------------------------------------------- #


def test_sanitize_windows_path_on_posix_redacts_username():
    label = sanitize_executable_location(
        r"C:\Users\SecretUser\AppData\Local\Programs\cursor\cursor.cmd"
    )
    assert "SecretUser" not in label
    assert label.endswith("cursor.cmd")
    assert "PATH=" not in label


def test_sanitize_unc_path_redacts_middle():
    label = sanitize_executable_location(r"\\fileserver\team\SecretUser\tool.exe")
    assert "SecretUser" not in label
    assert label.endswith("tool.exe")


def test_sanitize_posix_path_still_classifies():
    label = sanitize_executable_location("/usr/local/bin/codex")
    assert label.endswith("codex")
    assert "SecretUser" not in label


def test_sanitize_is_deterministic():
    p = r"C:\Users\Someone\bin\claude.cmd"
    assert sanitize_executable_location(p) == sanitize_executable_location(p)


# --------------------------------------------------------------------------- #
# B. targeted / related-module test selection
# --------------------------------------------------------------------------- #


def _make_pkg_repo(root: Path) -> Path:
    (root / "src" / "ai_dev_os").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "src" / "ai_dev_os" / "__init__.py").write_text("__version__='0.0.0'\n", encoding="utf-8")
    (root / "src" / "ai_dev_os" / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "ai_dev_os" / "gadget.py").write_text("OTHER = 2\n", encoding="utf-8")
    (root / "tests" / "test_widget.py").write_text(
        "from ai_dev_os.widget import VALUE\n\ndef test_value():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_uses_widget.py").write_text(
        "from ai_dev_os.widget import VALUE\n\ndef test_uses():\n    assert VALUE\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_unrelated.py").write_text(
        "def test_nothing():\n    assert True\n",
        encoding="utf-8",
    )
    return root


def test_select_direct_and_importers(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = select_related_tests(root, ["src/ai_dev_os/widget.py"])
    assert sel.reason == "related"
    assert "tests/test_widget.py" in sel.selected_tests
    assert "tests/test_uses_widget.py" in sel.selected_tests
    assert "tests/test_unrelated.py" not in sel.selected_tests


def test_select_changed_test_file(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = select_related_tests(root, ["tests/test_unrelated.py"])
    assert sel.selected_tests == ["tests/test_unrelated.py"]
    assert sel.reason == "related"


def test_broad_impact_selects_all(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = select_related_tests(root, ["src/ai_dev_os/__init__.py"])
    assert sel.broad is True
    assert sel.reason == "broad_impact"
    assert set(sel.selected_tests) == {
        "tests/test_widget.py",
        "tests/test_uses_widget.py",
        "tests/test_unrelated.py",
    }


def test_no_code_impact(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    (root / "README.md").write_text("# docs\n", encoding="utf-8")
    sel = select_related_tests(root, ["README.md"])
    assert sel.selected_tests == []
    assert sel.reason == "no_code_impact"


def test_no_related_tests_found(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = select_related_tests(root, ["src/ai_dev_os/gadget.py"])
    assert sel.selected_tests == []
    assert sel.reason == "no_related_tests_found"
    assert "src/ai_dev_os/gadget.py" in sel.unmapped_sources


def test_selection_is_deterministic(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    a = select_related_tests(root, ["src/ai_dev_os/widget.py", "src/ai_dev_os/gadget.py"])
    b = select_related_tests(root, ["src/ai_dev_os/gadget.py", "src/ai_dev_os/widget.py"])
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def test_run_targeted_tests_executes(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = select_related_tests(root, ["tests/test_unrelated.py"])
    run = run_targeted_tests(root, sel, policy=CIPolicy())
    assert run.final_verdict in {CIVerdict.PASS.value, CIVerdict.PASS_WITH_NOTES.value}
    assert run.tests_failed == 0
    assert run.command_identity.endswith("<targeted>")
    assert run.ran_full_suite is False


def test_run_targeted_no_selection_skips_without_running(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = TargetedSelection(reason="no_code_impact")
    run = run_targeted_tests(root, sel, policy=CIPolicy(), fallback_full=False)
    assert run.final_verdict == CIVerdict.PASS_WITH_NOTES.value
    assert run.tests_passed is None  # never executed
    assert "no related tests" in run.next_action


def test_run_targeted_all_filtered_fails_closed(tmp_path: Path):
    """Non-empty selection that is entirely unsafe must NOT run the whole suite."""
    root = _make_pkg_repo(tmp_path)
    sel = TargetedSelection(
        reason="related",
        selected_tests=["tests/does_not_exist.py", "src/ai_dev_os/widget.py"],
    )
    run = run_targeted_tests(root, sel, policy=CIPolicy())
    assert run.final_verdict == CIVerdict.FAIL.value
    assert run.failure_class == "command_rejected"
    assert run.tests_passed is None


def test_run_targeted_serialization_deterministic(tmp_path: Path):
    root = _make_pkg_repo(tmp_path)
    sel = select_related_tests(root, ["tests/test_unrelated.py"])
    run = run_targeted_tests(root, sel, policy=CIPolicy())
    # to_dict() must be stable for the same envelope (field order via sort_keys).
    assert json.dumps(run.to_dict(), sort_keys=True) == json.dumps(run.to_dict(), sort_keys=True)


def test_default_broad_globs_include_config_and_schemas():
    assert "config/**" in DEFAULT_BROAD_IMPACT_GLOBS
    assert "schemas/**" in DEFAULT_BROAD_IMPACT_GLOBS
    assert "src/ai_dev_os/cli.py" in DEFAULT_BROAD_IMPACT_GLOBS


# --------------------------------------------------------------------------- #
# C. history + comparison
# --------------------------------------------------------------------------- #


def _write_run(root: Path, run_id: str, *, started: str, verdict: str, fcs, failed=0):
    runs_dir = root / "workspace" / "ci_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "4a.1",
        "ci_policy_version": "4a.1",
        "run_id": run_id,
        "repository_identity": str(root),
        "starting_commit": "abc123",
        "trigger_type": "local",
        "state": "completed",
        "started_at": started,
        "finished_at": started,
        "duration_seconds": 1.0,
        "stages": [],
        "final_verdict": verdict,
        "failure_classes": list(fcs),
        "human_review_required": False,
        "blocker": bool(fcs),
        "next_action": "",
        "policy_decision": "allow",
        "tests_passed": 10,
        "tests_failed": failed,
        "tests_skipped": 0,
        "sanitized_notes": [],
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_list_runs_empty(tmp_path: Path):
    assert list_runs(tmp_path) == []


def test_list_runs_orders_recent_first(tmp_path: Path):
    _write_run(tmp_path, "ci_a", started="2026-07-20T00:00:00+00:00", verdict="pass", fcs=[])
    _write_run(tmp_path, "ci_b", started="2026-07-22T00:00:00+00:00", verdict="fail", fcs=["tests_failed"], failed=1)
    entries = list_runs(tmp_path)
    assert [e.run_id for e in entries] == ["ci_b", "ci_a"]
    assert entries[0].final_verdict == "fail"


def test_list_runs_tolerates_malformed_and_future_schema(tmp_path: Path):
    _write_run(tmp_path, "ci_ok", started="2026-07-20T00:00:00+00:00", verdict="pass", fcs=[])
    runs_dir = tmp_path / "workspace" / "ci_runs"
    (runs_dir / "broken.json").write_text("{ not valid json", encoding="utf-8")
    (runs_dir / "future.json").write_text(
        json.dumps({"schema_version": "9z.9", "run_id": "ci_future", "final_verdict": "pass",
                    "failure_classes": [], "started_at": "2026-07-25T00:00:00+00:00"}),
        encoding="utf-8",
    )
    entries = list_runs(tmp_path)
    by_id = {e.run_id: e for e in entries}
    assert by_id["broken"].readable is False
    assert by_id["ci_future"].readable is True
    assert "9z.9" in by_id["ci_future"].note  # surfaced, not crashed


def test_latest_passing_run(tmp_path: Path):
    _write_run(tmp_path, "ci_old_pass", started="2026-07-19T00:00:00+00:00", verdict="pass", fcs=[])
    _write_run(tmp_path, "ci_new_fail", started="2026-07-21T00:00:00+00:00", verdict="fail", fcs=["tests_failed"], failed=2)
    entry = latest_passing_run(tmp_path)
    assert entry is not None and entry.run_id == "ci_old_pass"


def test_compare_runs_detects_regression():
    base = {"run_id": "b", "final_verdict": "pass", "failure_classes": [], "tests_failed": 0}
    head = {"run_id": "h", "final_verdict": "fail", "failure_classes": ["tests_failed"], "tests_failed": 3}
    cmp = compare_runs(base, head)
    assert cmp.regressed is True
    assert cmp.improved is False
    assert cmp.new_failure_classes == ["tests_failed"]
    assert cmp.tests_failed_delta == 3
    assert cmp.summary.startswith("REGRESSION")


def test_compare_runs_detects_improvement():
    base = {"run_id": "b", "final_verdict": "fail", "failure_classes": ["tests_failed", "secret_pattern_detected"], "tests_failed": 2}
    head = {"run_id": "h", "final_verdict": "pass", "failure_classes": [], "tests_failed": 0}
    cmp = compare_runs(base, head)
    assert cmp.regressed is False
    assert cmp.improved is True
    assert set(cmp.resolved_failure_classes) == {"tests_failed", "secret_pattern_detected"}
    assert cmp.summary.startswith("IMPROVED")


def test_compare_runs_no_change():
    base = {"run_id": "b", "final_verdict": "pass", "failure_classes": [], "tests_failed": 0}
    head = {"run_id": "h", "final_verdict": "pass", "failure_classes": [], "tests_failed": 0}
    cmp = compare_runs(base, head)
    assert cmp.regressed is False and cmp.improved is False
    assert cmp.summary.startswith("NO CHANGE")


def test_compare_to_previous(tmp_path: Path):
    _write_run(tmp_path, "ci_1", started="2026-07-20T00:00:00+00:00", verdict="pass", fcs=[])
    _write_run(tmp_path, "ci_2", started="2026-07-21T00:00:00+00:00", verdict="fail", fcs=["dependency_policy_violated"], failed=0)
    cmp = compare_to_previous(tmp_path)
    assert cmp is not None
    assert cmp.base_run_id == "ci_1"
    assert cmp.head_run_id == "ci_2"
    assert cmp.regressed is True


def test_comparison_serialization_deterministic():
    base = {"run_id": "b", "final_verdict": "pass", "failure_classes": [], "tests_failed": 0}
    head = {"run_id": "h", "final_verdict": "fail", "failure_classes": ["x", "y"], "tests_failed": 1}
    c1 = compare_runs(base, head)
    c2 = compare_runs(base, head)
    assert json.dumps(c1.to_dict(), sort_keys=True) == json.dumps(c2.to_dict(), sort_keys=True)
    assert isinstance(c1, CIRunComparison)


def test_load_run_missing_returns_none(tmp_path: Path):
    assert load_run(tmp_path, "nope") is None


# --------------------------------------------------------------------------- #
# D. report rendering
# --------------------------------------------------------------------------- #


def _sample_run() -> CIRun:
    return CIRun(
        run_id="ci_sample01",
        repository_identity="/repo",
        starting_commit="deadbeefcafe0000",
        trigger_type="local",
        state="failed",
        duration_seconds=12.5,
        final_verdict=CIVerdict.FAIL.value,
        failure_classes=["tests_failed"],
        next_action="fix failing tests before merge",
        tests_passed=100,
        tests_failed=2,
        tests_skipped=1,
        stages=[
            CIStageResult(
                stage_name="pytest_suite",
                command_identity="python -m pytest -q",
                validation_status=CIStageStatus.FAILED.value,
                failure_class="tests_failed",
                duration_seconds=9.1,
                sanitized_output_summary="2 failed, 100 passed\nassert 1 == 2",
                files_examined=["tests/test_x.py"],
                blocker=True,
                next_action="fix failing tests before merge",
            ),
            CIStageResult(
                stage_name="secret_scan",
                command_identity="scan_files tracked",
                validation_status=CIStageStatus.SKIPPED.value,
                sanitized_output_summary="skipped by operator",
            ),
        ],
    )


def test_render_ci_summary_contains_required_fields():
    md = render_ci_summary(_sample_run(), artifact_path="workspace/ci_runs/ci_sample01.json")
    for token in (
        "ci_sample01",              # audit id
        "fail",                     # verdict
        "pytest_suite",             # executed stage
        "python -m pytest -q",      # command executed
        "workspace/ci_runs/ci_sample01.json",  # artifact location
        "Failure reasons",          # failure section
        "Skipped stages",           # skipped section
        "deadbeefcafe",             # starting commit (truncated)
    ):
        assert token in md, token


def test_render_ci_summary_is_deterministic():
    run = _sample_run()
    assert render_ci_summary(run) == render_ci_summary(run)


def test_render_ci_summary_no_artifact_label():
    md = render_ci_summary(_sample_run())
    assert "(not persisted)" in md


def test_render_targeted_summary():
    run_dict = {
        "run_id": "cisel_x",
        "final_verdict": "pass_with_notes",
        "ran_full_suite": False,
        "tests_passed": 5,
        "tests_failed": 0,
        "tests_skipped": 0,
        "duration_seconds": 1.2,
        "next_action": "run full ci-check",
        "selection": {
            "reason": "related",
            "selected_tests": ["tests/test_a.py", "tests/test_b.py"],
            "unmapped_sources": ["src/ai_dev_os/z.py"],
        },
    }
    md = render_targeted_summary(run_dict)
    assert "tests/test_a.py" in md
    assert "no related test" in md.lower()
    assert "src/ai_dev_os/z.py" in md


def test_render_comparison():
    cmp = compare_runs(
        {"run_id": "b", "final_verdict": "pass", "failure_classes": [], "tests_failed": 0},
        {"run_id": "h", "final_verdict": "fail", "failure_classes": ["tests_failed"], "tests_failed": 1},
    )
    md = render_comparison(cmp.to_dict())
    assert "REGRESSION" in md
    assert "New failure classes" in md
    assert "tests_failed" in md


# --------------------------------------------------------------------------- #
# CLI wiring + compatibility / boundary guarantees
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cli(*args: str) -> subprocess.CompletedProcess:
    import sys

    return subprocess.run(
        [sys.executable, "-m", "ai_dev_os.cli", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cli_new_commands_registered():
    from ai_dev_os.cli import build_parser

    parser = build_parser()
    for cmd in ("ci-targeted", "ci-history", "ci-compare"):
        args = parser.parse_args([cmd])
        assert args.command == cmd


def test_cli_ci_check_accepts_format_flag():
    from ai_dev_os.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["ci-check", "--format", "md"])
    assert args.format == "md"


def test_cli_ci_targeted_select_only_runs():
    proc = _cli("ci-targeted", "--changed-file", "src/ai_dev_os/routing.py", "--select-only")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert "tests/test_routing.py" in payload["selected_tests"]


def test_cli_ci_history_empty_or_list():
    proc = _cli("ci-history", "--limit", "5")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert isinstance(payload, list)


def test_stage_order_unchanged_by_hardening():
    # The additive hardening must NOT alter the fixed Round 4A pipeline.
    assert STAGE_ORDER == (
        "repo_identity",
        "python_compile",
        "pytest_suite",
        "git_diff_check",
        "schema_validation",
        "config_parse",
        "project_registry",
        "prohibited_paths",
        "package_version",
        "dependency_policy",
        "secret_scan",
        "runtime_artifacts",
        "doc_consistency",
        "finalize",
    )


def test_new_schemas_are_structurally_valid():
    for name in ("ci_targeted_run.schema.json", "ci_run_comparison.schema.json"):
        data = json.loads((REPO_ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "$schema" in data
        assert any(k in data for k in ("properties", "type", "$ref"))


def test_no_new_runtime_dependencies():
    import tomllib

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = data["project"]["dependencies"]
    # Hardening adds only stdlib usage; runtime deps stay PyYAML-only.
    assert [d for d in runtime if not d.lower().startswith("pyyaml")] == []
