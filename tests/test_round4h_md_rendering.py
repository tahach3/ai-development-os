"""Round 4H — Markdown rendering parity for ci-boundaries / validate-change."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ai_dev_os import __version__
from ai_dev_os.ci_boundaries import BoundaryCheckResult, BoundaryFinding
from ai_dev_os.ci_models import PRValidationFinding, PRValidationSummary
from ai_dev_os.ci_report import render_boundary_summary, render_validate_change_summary
from ai_dev_os.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ai_dev_os.cli", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _ok_boundary() -> BoundaryCheckResult:
    return BoundaryCheckResult(
        ok=True,
        findings=[],
        failure_classes=[],
        files_examined=["demo_projects/calculator-demo/calculator/ops.py"],
    )


def _fail_boundary() -> BoundaryCheckResult:
    return BoundaryCheckResult(
        ok=False,
        findings=[
            BoundaryFinding(
                path="demo_projects/calculator-demo/leak.py",
                project_id="calculator-demo",
                reason="cross_boundary_import",
                failure_class="boundary_violation",
                detail="import/path ref 'src/ai_dev_os/x' crosses into project 'ai-dev-os'",
                blocker=True,
            )
        ],
        failure_classes=["boundary_violation"],
        files_examined=["demo_projects/calculator-demo/leak.py"],
    )


def _sample_validate_summary() -> PRValidationSummary:
    return PRValidationSummary(
        schema_version="4a.1",
        ci_policy_version="1.0",
        run_id="vc_sample01",
        repository_identity=str(REPO_ROOT),
        starting_commit="deadbeefcafe",
        compared_base_commit="cafebabe0001",
        trigger_type="validate_change",
        started_at="2026-07-24T00:00:00Z",
        finished_at="2026-07-24T00:00:01Z",
        duration_seconds=1.25,
        files_examined=["src/ai_dev_os/cli.py"],
        findings=[
            PRValidationFinding(
                path="src/ai_dev_os/cli.py",
                category="safety_critical",
                severity="major",
                summary="safety-critical policy/path change requires human review",
                failure_class="human_review_required",
                human_review_required=True,
                blocker=False,
            )
        ],
        final_verdict="human_review_required",
        failure_classes=["human_review_required"],
        human_review_required=True,
        blocker=False,
        next_action="human review required; no automatic approve/merge",
        policy_decision="human_review",
    )


def test_render_boundary_summary_ok_fields():
    md = render_boundary_summary(_ok_boundary())
    for token in (
        "# Boundary check",
        "**OK:** true",
        "Files examined",
        "demo_projects/calculator-demo/calculator/ops.py",
        "(none)",
        "No automatic merge or deploy",
    ):
        assert token in md, token


def test_render_boundary_summary_fail_fields():
    md = render_boundary_summary(_fail_boundary())
    for token in (
        "**OK:** false",
        "boundary_violation",
        "cross_boundary_import",
        "calculator-demo",
        "leak.py",
        "blocker=true",
        "## Findings",
    ):
        assert token in md, token


def test_render_boundary_summary_deterministic():
    result = _fail_boundary()
    assert render_boundary_summary(result) == render_boundary_summary(result)
    assert render_boundary_summary(result) == render_boundary_summary(result.to_dict())


def test_render_validate_change_summary_fields():
    md = render_validate_change_summary(_sample_validate_summary())
    for token in (
        "# Validate change `vc_sample01`",
        "**Verdict:** `human_review_required`",
        "validate_change",
        "deadbeefcafe",
        "cafebabe0001",
        "safety_critical",
        "human_review_required",
        "**Auto-approve:** false",
        "**Auto-merge:** false",
        "## Findings",
        "## Failure classes",
        "No automatic merge or approve",
        "4a.1",
    ):
        assert token in md, token


def test_render_validate_change_summary_deterministic():
    summary = _sample_validate_summary()
    assert render_validate_change_summary(summary) == render_validate_change_summary(summary)
    assert render_validate_change_summary(summary) == render_validate_change_summary(
        summary.to_dict()
    )


def test_parser_format_flags_default_json():
    parser = build_parser()
    bound = parser.parse_args(["ci-boundaries", "--path", "x.py"])
    assert bound.format == "json"
    vc = parser.parse_args(["validate-change", "--base", "HEAD"])
    assert vc.format == "json"
    bound_md = parser.parse_args(["ci-boundaries", "--format", "md", "--path", "x.py"])
    assert bound_md.format == "md"
    vc_md = parser.parse_args(["validate-change", "--base", "HEAD", "--format", "md"])
    assert vc_md.format == "md"


def test_cli_ci_boundaries_format_md_vs_json():
    path = "demo_projects/calculator-demo/calculator/ops.py"
    md_proc = _cli("ci-boundaries", "--path", path, "--format", "md")
    assert md_proc.returncode == 0, md_proc.stderr
    assert "# Boundary check" in md_proc.stdout
    assert "**OK:**" in md_proc.stdout

    json_proc = _cli("ci-boundaries", "--path", path)
    assert json_proc.returncode == 0, json_proc.stderr
    payload = json.loads(json_proc.stdout)
    assert "ok" in payload
    assert "findings" in payload
    assert "files_examined" in payload
    assert "failure_classes" in payload


def test_cli_validate_change_format_md_vs_json():
    md_proc = _cli("validate-change", "--base", "HEAD", "--format", "md")
    assert md_proc.returncode == 0, md_proc.stderr
    assert "Validate change" in md_proc.stdout
    assert "**Verdict:**" in md_proc.stdout
    assert "**Auto-merge:** false" in md_proc.stdout

    json_proc = _cli("validate-change", "--base", "HEAD")
    assert json_proc.returncode == 0, json_proc.stderr
    payload = json.loads(json_proc.stdout)
    for key in (
        "schema_version",
        "run_id",
        "final_verdict",
        "findings",
        "files_examined",
        "auto_approve",
        "auto_merge",
    ):
        assert key in payload
    assert payload["auto_approve"] is False
    assert payload["auto_merge"] is False


def test_package_version_round4h():
    assert __version__ == "0.8.11"
