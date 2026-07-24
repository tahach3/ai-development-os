"""Round 4C evidence-first reporting tests (synthetic calculator-demo / temp repos)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_dev_os import __version__
from ai_dev_os.cli import main
from ai_dev_os.models import ImplementationReport, ReportOutcome, utc_now_iso
from ai_dev_os.reporting_builder import (
    EvidenceBundle,
    ReportingBuildError,
    build_canonical_report,
)
from ai_dev_os.reporting_constants import (
    EVIDENCE_SCHEMA_VERSION,
    REDACTION_POLICY_VERSION,
    RELEVANCE_POLICY_VERSION,
    RENDERER_VERSION,
    REPORT_POLICY_VERSION,
    REPORT_SCHEMA_VERSION,
)
from ai_dev_os.reporting_fingerprints import compute_report_fingerprint, source_set_fingerprint
from ai_dev_os.reporting_legacy import adapt_implementation_report, adapt_partial_legacy
from ai_dev_os.reporting_models import (
    AcceptanceCriterionRow,
    AuthorityLevel,
    AvailabilityState,
    ClaimRecord,
    ClaimStatus,
    CriterionStatus,
    DetailLevel,
    EvidenceItem,
    EvidenceType,
    NextAction,
    ReportAudience,
    ReportStatus,
    RiskRecord,
    RootCauseConfidence,
    RootCauseRecord,
    SecurityFinding,
    SecuritySeverity,
    UsageEvidenceState,
    UsageField,
    new_evidence_id,
)
from ai_dev_os.reporting_redaction import sanitize_text, strip_ansi
from ai_dev_os.reporting_renderer import render_markdown
from ai_dev_os.reporting_store import CanonicalReportStore
from ai_dev_os.reporting_validate import is_stale_against, validate_snapshot


FIXED_TS = "2026-07-22T12:00:00+00:00"


def _ev(
    eid: str,
    etype: EvidenceType,
    value: dict,
    *,
    authority: AuthorityLevel = AuthorityLevel.AUTHORITATIVE_PERSISTED,
    status: ClaimStatus = ClaimStatus.VERIFIED,
    availability: AvailabilityState = AvailabilityState.AVAILABLE,
) -> EvidenceItem:
    item = EvidenceItem(
        evidence_id=eid,
        evidence_type=etype,
        source_type="synthetic",
        source_record_type=etype.value,
        source_record_id=eid,
        structured_value=value,
        safe_summary=f"{etype.value}:{eid}",
        authority_level=authority,
        verification_status=status,
        availability_state=availability,
        collected_at=FIXED_TS,
        effective_at=FIXED_TS,
        producer_version=__version__,
    )
    item.compute_integrity_hash()
    return item


def _base_bundle(**overrides) -> EvidenceBundle:
    evidence = [
        _ev(
            "ev_task",
            EvidenceType.TASK,
            {"title": "Add multiply", "status": "completed"},
        ),
        _ev(
            "ev_impl",
            EvidenceType.IMPLEMENTATION_RESULT,
            {"outcome": "success", "files": ["calc.py"]},
        ),
        _ev(
            "ev_test_targeted",
            EvidenceType.TARGETED_TEST_RESULT,
            {
                "scope": "targeted",
                "passed_count": 3,
                "failed_count": 0,
                "skipped_count": 1,
                "status": "passed",
            },
        ),
        _ev(
            "ev_test_full",
            EvidenceType.FULL_TEST_RESULT,
            {
                "scope": "full",
                "passed_count": 10,
                "failed_count": 0,
                "skipped_count": 2,
                "status": "passed",
            },
        ),
        _ev(
            "ev_review",
            EvidenceType.REVIEW_VERDICT,
            {"verdict": "pass"},
        ),
        _ev(
            "ev_ci",
            EvidenceType.CI_RUN,
            {"status": "passed", "conclusion": "pass", "run_id": "ci_local_1"},
        ),
    ]
    data = dict(
        project_id="calculator-demo",
        task_id="task_multiply",
        task_objective="Add multiply operation to calculator-demo",
        outcome="Implementation completed with passing tests and review",
        final_verdict="pass",
        plan_id="plan_1",
        starting_commit="aaa111",
        final_commit="bbb222",
        repository_identity="calculator-demo",
        evidence=evidence,
        claims=[
            ClaimRecord(
                claim_id="cl_impl_ok",
                text="Implementation succeeded",
                status=ClaimStatus.VERIFIED,
                evidence_ids=["ev_impl", "ev_test_full"],
            ),
            ClaimRecord(
                claim_id="cl_review_ok",
                text="Review passed",
                status=ClaimStatus.VERIFIED,
                evidence_ids=["ev_review"],
            ),
        ],
        acceptance=[
            AcceptanceCriterionRow(
                criterion_id="ac_1",
                criterion_text="multiply works",
                status=CriterionStatus.PASSED,
                claim_status=ClaimStatus.VERIFIED,
                evidence_ids=["ev_test_full"],
                verification_method="pytest",
                verifier="ci",
            )
        ],
        approvals=[
            {
                "approval_id": "ap_1",
                "type": "plan",
                "approver": "owner",
                "validity": "valid",
                "approved_fingerprint": "fp_plan_1",
                "current_fingerprint": "fp_plan_1",
            }
        ],
        risks=[],
        blockers=[],
        next_actions=[
            NextAction(
                action_id="na_1",
                text="Close task after operator confirmation",
                action_type="operator",
                required=False,
                order=1,
            )
        ],
        git_intelligence={
            "branch": "master",
            "files_added": [],
            "files_modified": ["calc.py", "tests/test_calc.py"],
            "files_deleted": [],
            "file_categories": ["code", "test"],
            "dirty": False,
        },
        test_intelligence={
            "scope": "full",
            "summary": "passed=10, failed=0, skipped=2",
            "passed_count": 10,
            "failed_count": 0,
            "skipped_count": 2,
            "xfailed_count": 0,
            "targeted": False,
            "attempts": [
                {"attempt": 1, "passed_count": 10, "failed_count": 0, "skipped_count": 2}
            ],
        },
        ci_intelligence={
            "provider": "local",
            "run_id": "ci_local_1",
            "status": "passed",
            "conclusion": "pass",
            "summary": "local CI passed",
            "remote_status": "unavailable",
        },
        dependency_intelligence={
            "files_examined": ["pyproject.toml"],
            "policy_verdict": "pass",
            "added": [],
            "removed": [],
        },
        provider_orchestration={
            "execution_mode": "simulation",
            "provider_id": "simulated",
            "review_verdict": "pass",
            "repair_rounds": 0,
        },
        source_bindings={
            "task_fingerprint": "tf_1",
            "plan_fingerprint": "pf_1",
            "approval_fingerprint": "af_1",
        },
        generated_at=FIXED_TS,
    )
    data.update(overrides)
    return EvidenceBundle(**data)


def test_package_version_round4c():
    assert __version__ == "0.8.10"


def test_canonical_evidence_and_report_serialization():
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.FULL
    )
    data = snap.to_dict()
    again = type(snap).from_dict(data)
    assert again.report_id == snap.report_id
    assert again.to_dict()["evidence_manifest"][0]["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert again.schema_version == REPORT_SCHEMA_VERSION


def test_deterministic_report_ids_and_fingerprints():
    a = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
    )
    b = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
    )
    assert a.report_id == b.report_id
    assert a.report_fingerprint == b.report_fingerprint
    assert a.source_set_fingerprint == b.source_set_fingerprint
    # Fingerprint excludes generated_at volatility — same bindings yield same fp
    assert compute_report_fingerprint(a) == a.report_fingerprint


def test_duplicate_and_dangling_evidence():
    bundle = _base_bundle()
    bundle.evidence.append(bundle.evidence[0])
    with pytest.raises(ReportingBuildError, match="duplicate"):
        build_canonical_report(
            bundle, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
        )
    bundle = _base_bundle()
    bundle.claims[0].evidence_ids = ["missing_ev"]
    with pytest.raises(ReportingBuildError, match="dangling"):
        build_canonical_report(
            bundle, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
        )


def test_claim_status_rules():
    bundle = _base_bundle()
    bundle.claims.append(
        ClaimRecord(
            claim_id="cl_inf",
            text="Inferred completeness",
            status=ClaimStatus.INFERRED,
            evidence_ids=["ev_test_full"],
            inference_rule_id="inf.tests_and_review",
        )
    )
    bundle.claims.append(
        ClaimRecord(
            claim_id="cl_na",
            text="Remote deploy",
            status=ClaimStatus.NOT_APPLICABLE,
            applicability_reason="No deploy stage in Round 4C",
        )
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.AUDITOR, detail_level=DetailLevel.AUDIT
    )
    assert any(c.status is ClaimStatus.INFERRED for c in snap.claim_records)

    bad = _base_bundle()
    bad.claims.append(
        ClaimRecord(
            claim_id="bad_inf",
            text="x",
            status=ClaimStatus.INFERRED,
            evidence_ids=["ev_test_full"],
        )
    )
    with pytest.raises(ReportingBuildError, match="inferred"):
        build_canonical_report(
            bad, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
        )

    bad2 = _base_bundle()
    bad2.claims.append(
        ClaimRecord(claim_id="bad_v", text="x", status=ClaimStatus.VERIFIED, evidence_ids=[])
    )
    with pytest.raises(ReportingBuildError, match="verified"):
        build_canonical_report(
            bad2, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
        )


def test_scenario_direct_success():
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.FULL
    )
    assert snap.report_status in (ReportStatus.COMPLETE, ReportStatus.COMPLETE_WITH_NOTES)
    assert snap.test_intelligence["skipped_count"] == 2
    assert snap.dependency_intelligence["vulnerability_scan"] == "unavailable"
    assert "simulation" in (snap.provider_orchestration.get("execution_mode") or "")


def test_scenario_one_repair_success():
    bundle = _base_bundle(
        repair_history=[
            {
                "repair_round_number": 1,
                "triggering_findings": ["test_fail"],
                "files_changed": ["calc.py"],
                "tests_rerun": ["tests/test_calc.py"],
                "review_result": "pass",
                "progress_fingerprint": "prog_1",
                "scope_change_status": "unchanged",
                "reapproval_status": "not_required",
                "final_outcome": "success",
            }
        ],
        test_intelligence={
            "scope": "full",
            "summary": "passed=10 after repair; earlier failed=1",
            "passed_count": 10,
            "failed_count": 0,
            "skipped_count": 2,
            "attempts": [
                {"attempt": 1, "passed_count": 9, "failed_count": 1, "skipped_count": 2},
                {"attempt": 2, "passed_count": 10, "failed_count": 0, "skipped_count": 2},
            ],
        },
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.FULL
    )
    md = render_markdown(snap)
    assert "repair" in md.lower()
    assert "attempt" in json.dumps(snap.test_intelligence)


def test_scenario_stalemate_block():
    bundle = _base_bundle(
        workflow_blocked=True,
        blockers=["Orchestration stalemate: repeated no-progress evidence"],
        outcome="Blocked by stalemate",
        final_verdict="blocked",
        next_actions=[
            NextAction(
                action_id="na_block",
                text="Inspect stalemate evidence and decide manually",
                action_type="operator",
                required=True,
                order=1,
            )
        ],
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.OPERATOR, detail_level=DetailLevel.STANDARD
    )
    assert snap.report_status is ReportStatus.BLOCKED
    md = render_markdown(snap)
    assert "stalemate" in md.lower()
    assert "completed successfully" not in md.lower()


def test_scenario_missing_evidence_unavailable():
    bundle = _base_bundle(
        unavailable_mandatory=["remote_ci", "provider_usage"],
        usage_fields=[
            UsageField(name="input_tokens", state=UsageEvidenceState.UNAVAILABLE, value=None)
        ],
        ci_intelligence={
            "provider": "local",
            "status": "passed",
            "summary": "local passed",
            "remote_status": "unavailable",
        },
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.OPERATOR, detail_level=DetailLevel.STANDARD
    )
    assert snap.report_status is ReportStatus.INCOMPLETE
    assert snap.usage_fields[0].value is None
    assert snap.usage_fields[0].state is UsageEvidenceState.UNAVAILABLE
    md = render_markdown(snap)
    assert "unavailable" in md.lower()
    assert "input_tokens: 0" not in md


def test_scenario_conflicting_evidence():
    bundle = _base_bundle()
    # Replace test evidence with failure while impl claims success
    bundle.evidence = [
        e
        if e.evidence_id != "ev_test_full"
        else _ev(
            "ev_test_full",
            EvidenceType.FULL_TEST_RESULT,
            {"scope": "full", "passed_count": 8, "failed_count": 2, "skipped_count": 0, "status": "failed"},
            authority=AuthorityLevel.AUTHORITATIVE_PERSISTED,
        )
        for e in bundle.evidence
    ]
    bundle.test_intelligence = {
        "summary": "failed=2",
        "passed_count": 8,
        "failed_count": 2,
        "skipped_count": 0,
        "failing_tests": ["test_multiply"],
    }
    snap = build_canonical_report(
        bundle, audience=ReportAudience.INDEPENDENT_REVIEWER, detail_level=DetailLevel.FULL
    )
    assert snap.report_status is ReportStatus.CONFLICTING_EVIDENCE
    assert snap.unresolved_conflicts
    md = render_markdown(snap)
    assert "conflict" in md.lower()


def test_scenario_stale_report(tmp_path: Path):
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
    )
    store = CanonicalReportStore(workspace_root=tmp_path)
    store.save_canonical(snap)
    loaded = store.load_canonical(snap.report_id)
    assert is_stale_against(loaded, {"task_fingerprint": "tf_CHANGED", **{
        k: v for k, v in loaded.source_bindings.items() if k != "task_fingerprint"
    }})
    result = validate_snapshot(
        loaded,
        current_bindings={
            "task_fingerprint": "tf_CHANGED",
            "plan_fingerprint": loaded.source_bindings["plan_fingerprint"],
            "approval_fingerprint": loaded.source_bindings["approval_fingerprint"],
            "starting_commit": loaded.starting_commit,
            "final_commit": loaded.final_commit,
            "report_policy_version": REPORT_POLICY_VERSION,
            "relevance_policy_version": RELEVANCE_POLICY_VERSION,
            "redaction_policy_version": REDACTION_POLICY_VERSION,
        },
    )
    assert result.report_status is ReportStatus.STALE


def test_scenario_executive_summary_blocker_visible():
    bundle = _base_bundle(
        blockers=["Missing required approval"],
        risks=[
            RiskRecord(
                risk_id="rk_1",
                category="approval",
                severity=SecuritySeverity.CRITICAL,
                description="Approval invalidated",
                blocking=True,
                evidence_ids=["ev_task"],
            )
        ],
        approvals=[
            {
                "approval_id": "ap_1",
                "validity": "invalidated",
                "invalidation_reason": "plan fingerprint changed",
            }
        ],
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.EXECUTIVE, detail_level=DetailLevel.SUMMARY
    )
    md = render_markdown(snap)
    assert "approval" in md.lower() or "blocker" in md.lower() or "Missing" in md
    assert "perfect" not in md.lower()
    assert "fully secure" not in md.lower()
    # No long file lists
    assert "tests/test_calc.py" not in md or md.count("tests/test_calc.py") <= 1


def test_scenario_developer_full_detail():
    snap = build_canonical_report(
        _base_bundle(
            repair_history=[
                {
                    "repair_round_number": 1,
                    "final_outcome": "success",
                    "files_changed": ["calc.py"],
                    "tests_rerun": ["tests/test_calc.py"],
                }
            ]
        ),
        audience=ReportAudience.DEVELOPER,
        detail_level=DetailLevel.FULL,
    )
    md = render_markdown(snap)
    assert "calc.py" in md
    assert "Tests" in md
    assert "CI" in md


def test_scenario_auditor_no_secret_leak(tmp_path: Path):
    # Build synthetic secret material at runtime so tracked source avoids secret_scan hits.
    synth_key = "api_key=" + ("X" * 24)
    synth_password = "password=" + ("Y" * 20)
    bundle = _base_bundle()
    bundle.evidence.append(
        _ev(
            "ev_note",
            EvidenceType.HUMAN_DECISION,
            {"note": synth_key},
            authority=AuthorityLevel.OPERATOR_SUPPLIED,
            status=ClaimStatus.REPORTED,
        )
    )
    bundle.task_objective = f"Fix bug; {synth_password}"
    snap = build_canonical_report(
        bundle, audience=ReportAudience.AUDITOR, detail_level=DetailLevel.AUDIT
    )
    md = render_markdown(snap)
    assert ("Y" * 20) not in md
    assert snap.source_set_fingerprint
    assert REPORT_POLICY_VERSION in md
    assert "Audit appendix" in md


def test_scenario_documentation_only():
    bundle = _base_bundle(
        documentation_only=True,
        git_intelligence={
            "files_added": [],
            "files_modified": ["README.md", "docs/guide.md"],
            "files_deleted": [],
            "file_categories": ["documentation"],
        },
        provider_orchestration={"execution_mode": "simulation", "review_verdict": "pass"},
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
    )
    assert snap.documentation_only
    section_ids = [s.section_id for s in snap.section_records]
    assert "provider_orch" not in section_ids
    md = render_markdown(snap)
    assert "documentation-only" in md.lower()


def test_relevance_no_empty_or_duplicate_sections():
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.FULL
    )
    md = render_markdown(snap)
    ids = [s.section_id for s in snap.section_records if s.included]
    assert len(ids) == len(set(ids))
    # No empty ## headings: every ## has following content before next ## or EOF
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## "):
            rest = [l for l in lines[i + 1 :] if l.startswith("## ")]
            chunk = lines[i + 1 : (lines.index(rest[0]) if rest else len(lines))]
            assert any(c.strip() for c in chunk)


def test_usage_estimated_and_never_zero_fill():
    bundle = _base_bundle(
        usage_fields=[
            UsageField(
                name="total_tokens",
                state=UsageEvidenceState.ESTIMATED,
                value=100,
                method="fixture_estimate",
                assumptions="synthetic",
            )
        ]
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.OPERATOR, detail_level=DetailLevel.STANDARD
    )
    assert snap.usage_fields[0].state is UsageEvidenceState.ESTIMATED
    bad = _base_bundle(
        usage_fields=[
            UsageField(name="total_tokens", state=UsageEvidenceState.ESTIMATED, value=1)
        ]
    )
    with pytest.raises(ReportingBuildError, match="estimated"):
        build_canonical_report(
            bad, audience=ReportAudience.OPERATOR, detail_level=DetailLevel.STANDARD
        )


def test_root_cause_confidence_and_risks():
    bundle = _base_bundle(
        root_causes=[
            RootCauseRecord(
                root_cause_id="rc_1",
                observed_failure="test_multiply failed",
                failure_class="logic_error",
                confidence=RootCauseConfidence.PROBABLE,
                evidence_ids=["ev_test_full"],
                immediate_cause="off-by-one",
            )
        ],
        risks=[
            RiskRecord(
                risk_id="rk_low",
                category="tech_debt",
                severity=SecuritySeverity.LOW,
                description="Minor cleanup remaining",
                evidence_ids=["ev_impl"],
            )
        ],
    )
    snap = build_canonical_report(
        bundle, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.FULL
    )
    assert snap.root_causes[0].confidence is RootCauseConfidence.PROBABLE
    assert snap.report_status is ReportStatus.COMPLETE_WITH_NOTES


def test_acceptance_cannot_pass_on_reported_only():
    bundle = _base_bundle(
        acceptance=[
            AcceptanceCriterionRow(
                criterion_id="ac_bad",
                criterion_text="x",
                status=CriterionStatus.PASSED,
                claim_status=ClaimStatus.REPORTED,
                evidence_ids=["ev_impl"],
            )
        ]
    )
    with pytest.raises(ReportingBuildError, match="reported_only"):
        build_canonical_report(
            bundle, audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
        )


def test_secret_redaction_ansi_truncation():
    events = []
    token = "Bearer " + ("z" * 24)
    out = sanitize_text(
        token + "\x1b[31mred\x1b[0m",
        field_path="x",
        events=events,
    )
    assert ("z" * 24) not in out or "[REDACTED]" in out
    assert "\x1b" not in strip_ansi("\x1b[31mhi\x1b[0m")


def test_atomic_write_and_immutable(tmp_path: Path):
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
    )
    store = CanonicalReportStore(workspace_root=tmp_path)
    path = store.save_canonical(snap)
    assert path.exists()
    # Same fingerprint OK
    store.save_canonical(snap)
    # Different fingerprint refused
    snap2 = build_canonical_report(
        _base_bundle(outcome="Different outcome text"),
        audience=ReportAudience.DEVELOPER,
        detail_level=DetailLevel.STANDARD,
    )
    # May get different report_id; force same id collision
    snap2.report_id = snap.report_id
    with pytest.raises(FileExistsError):
        store.save_canonical(snap2)


def test_corrupted_report_handling(tmp_path: Path):
    store = CanonicalReportStore(workspace_root=tmp_path)
    path = store.canonical_path("rpt_corrupt")
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupted"):
        store.load_canonical("rpt_corrupt")


def test_legacy_adapters():
    report = ImplementationReport(
        task_id="task_x",
        summary="did stuff",
        files_changed=["a.py"],
        tests_run=["pytest"],
        outcome=ReportOutcome.SUCCESS,
    )
    ev = adapt_implementation_report(report)
    assert ev.verification_status is ClaimStatus.REPORTED
    assert ev.legacy_support is not None
    partial = adapt_partial_legacy({"id": "x"})
    assert partial.legacy_support.value == "insufficient_evidence"


def test_equitify_and_prohibited_rejection():
    with pytest.raises(ReportingBuildError):
        build_canonical_report(
            _base_bundle(project_id="equitify-machine"),
            audience=ReportAudience.DEVELOPER,
            detail_level=DetailLevel.STANDARD,
        )


def test_cli_build_render_validate_show(tmp_path: Path):
    bundle = _base_bundle()
    # Ensure evidence hashes present
    for e in bundle.evidence:
        e.compute_integrity_hash()
    evidence_path = tmp_path / "bundle.json"
    # Serialize via build then dump inputs
    from ai_dev_os.reporting_cli import evidence_bundle_from_dict

    raw = {
        "project_id": bundle.project_id,
        "task_id": bundle.task_id,
        "task_objective": bundle.task_objective,
        "outcome": bundle.outcome,
        "final_verdict": bundle.final_verdict,
        "plan_id": bundle.plan_id,
        "starting_commit": bundle.starting_commit,
        "final_commit": bundle.final_commit,
        "repository_identity": bundle.repository_identity,
        "evidence": [e.to_dict() for e in bundle.evidence],
        "claims": [c.to_dict() for c in bundle.claims],
        "acceptance": [a.to_dict() for a in bundle.acceptance],
        "approvals": bundle.approvals,
        "next_actions": [n.to_dict() for n in bundle.next_actions],
        "git_intelligence": bundle.git_intelligence,
        "test_intelligence": bundle.test_intelligence,
        "ci_intelligence": bundle.ci_intelligence,
        "dependency_intelligence": bundle.dependency_intelligence,
        "provider_orchestration": bundle.provider_orchestration,
        "source_bindings": bundle.source_bindings,
        "generated_at": FIXED_TS,
    }
    evidence_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    ws = tmp_path / "workspace"
    ws.mkdir()
    rc = main(
        [
            "build-report",
            "--evidence-bundle",
            str(evidence_path),
            "--audience",
            "executive",
            "--detail-level",
            "summary",
            "--workspace",
            str(ws),
        ]
    )
    assert rc == 0
    # discover report id
    store = CanonicalReportStore(workspace_root=ws)
    reports = list(store.canonical_dir.glob("*.json"))
    assert reports
    rid = reports[0].stem
    assert main(["validate-report", "--report-id", rid, "--workspace", str(ws)]) == 0
    assert (
        main(
            [
                "render-report",
                "--report-id",
                rid,
                "--workspace",
                str(ws),
                "--json",
            ]
        )
        == 0
    )
    assert main(["show-report", "--report-id", rid, "--workspace", str(ws), "--json"]) == 0


def test_policy_version_mismatch_stale():
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.STANDARD
    )
    result = validate_snapshot(
        snap,
        current_bindings={
            **snap.source_bindings,
            "report_policy_version": "99.0",
        },
    )
    assert any("stale_source:report_policy_version" in e for e in result.errors)


def test_coverage_unavailable_behavior():
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.DEVELOPER, detail_level=DetailLevel.FULL
    )
    md = render_markdown(snap)
    assert "coverage" in md.lower()
    assert "not measured" in md.lower() or "unavailable" in md.lower()


def test_no_live_provider_and_no_network_marker():
    snap = build_canonical_report(
        _base_bundle(), audience=ReportAudience.OPERATOR, detail_level=DetailLevel.STANDARD
    )
    assert snap.provider_orchestration.get("execution_mode") == "simulation"
    md = render_markdown(snap)
    assert "not a live model result" in md.lower() or "simulation" in md.lower()


def test_versions_independent():
    assert REPORT_SCHEMA_VERSION == "4c.1"
    assert EVIDENCE_SCHEMA_VERSION == "4c.1"
    assert REPORT_POLICY_VERSION == "4c.1"
    assert RELEVANCE_POLICY_VERSION == "4c.1"
    assert REDACTION_POLICY_VERSION == "4c.1"
    assert RENDERER_VERSION == "4c.1"
