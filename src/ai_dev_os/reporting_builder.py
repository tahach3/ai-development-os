"""Build canonical report snapshots from an evidence bundle (no LLM, no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import utc_now_iso
from .reporting_constants import (
    EQUITIFY_SENTINELS,
    REDACTION_POLICY_VERSION,
    RELEVANCE_POLICY_VERSION,
    RENDERER_VERSION,
    REPORT_POLICY_VERSION,
    REPORT_SCHEMA_VERSION,
)
from .reporting_fingerprints import compute_report_fingerprint, source_set_fingerprint
from .reporting_models import (
    AcceptanceCriterionRow,
    AuthorityLevel,
    AvailabilityState,
    CanonicalReportSnapshot,
    ClaimRecord,
    ClaimStatus,
    CriterionStatus,
    DetailLevel,
    EvidenceItem,
    EvidenceType,
    NextAction,
    PrivacyClassification,
    ReportAudience,
    ReportingFailureClass,
    ReportStatus,
    RetentionClass,
    RiskRecord,
    RootCauseRecord,
    SectionRecord,
    SecurityFinding,
    SecuritySeverity,
    UsageEvidenceState,
    UsageField,
    new_report_id,
)
from .reporting_redaction import sanitize_structure
from .reporting_relevance import SECTION_RULES, select_sections
from .reporting_summary import build_executive_summary


class ReportingBuildError(ValueError):
    """Fail-closed build error."""


@dataclass
class EvidenceBundle:
    """Operator/test-supplied evidence graph for deterministic report builds."""

    project_id: str
    task_id: str
    task_objective: str
    outcome: str = ""
    final_verdict: str = ""
    plan_id: str | None = None
    orchestration_id: str | None = None
    starting_commit: str | None = None
    final_commit: str | None = None
    repository_identity: str | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    claims: list[ClaimRecord] = field(default_factory=list)
    acceptance: list[AcceptanceCriterionRow] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    risks: list[RiskRecord] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[NextAction] = field(default_factory=list)
    root_causes: list[RootCauseRecord] = field(default_factory=list)
    security_findings: list[SecurityFinding] = field(default_factory=list)
    usage_fields: list[UsageField] = field(default_factory=list)
    git_intelligence: dict[str, Any] = field(default_factory=dict)
    test_intelligence: dict[str, Any] = field(default_factory=dict)
    ci_intelligence: dict[str, Any] = field(default_factory=dict)
    dependency_intelligence: dict[str, Any] = field(default_factory=dict)
    provider_orchestration: dict[str, Any] = field(default_factory=dict)
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any]] = field(default_factory=list)
    unavailable_mandatory: list[str] = field(default_factory=list)
    source_bindings: dict[str, Any] = field(default_factory=dict)
    documentation_only: bool = False
    workflow_blocked: bool = False
    legacy_marks: list[str] = field(default_factory=list)
    generated_at: str | None = None


def _reject_equitify(*parts: str | None) -> None:
    blob = " ".join(p or "" for p in parts).lower()
    for s in EQUITIFY_SENTINELS:
        if s in blob:
            raise ReportingBuildError(f"Prohibited Equitify identifier detected: {s}")


def _authority_rank(level: AuthorityLevel) -> int:
    order = {
        AuthorityLevel.AUTHORITATIVE_PERSISTED: 50,
        AuthorityLevel.DETERMINISTIC_DERIVED: 40,
        AuthorityLevel.OPERATOR_SUPPLIED: 30,
        AuthorityLevel.AGENT_REPORTED: 20,
        AuthorityLevel.EXTERNAL_UNVERIFIED: 10,
    }
    return order.get(level, 0)


def _validate_evidence_graph(evidence: list[EvidenceItem], claims: list[ClaimRecord]) -> None:
    ids = [e.evidence_id for e in evidence]
    if len(ids) != len(set(ids)):
        raise ReportingBuildError("duplicate_evidence_id")
    for ev in evidence:
        if ev.schema_version != REPORT_SCHEMA_VERSION and not str(ev.schema_version).startswith("4c."):
            # Allow only 4c.* evidence schemas in Round 4C builds
            if not ev.legacy_support:
                raise ReportingBuildError("unsupported_evidence_schema")
        if not ev.integrity_hash:
            ev.compute_integrity_hash()
    known = set(ids)
    for claim in claims:
        if claim.status is ClaimStatus.VERIFIED and not claim.evidence_ids:
            raise ReportingBuildError("verified_claim_requires_evidence")
        if claim.status is ClaimStatus.INFERRED and not claim.inference_rule_id:
            raise ReportingBuildError("inferred_claim_requires_rule")
        if claim.status is ClaimStatus.NOT_APPLICABLE and not claim.applicability_reason:
            raise ReportingBuildError("not_applicable_requires_reason")
        for eid in claim.evidence_ids:
            if eid not in known:
                raise ReportingBuildError(f"dangling_reference:{eid}")


def _detect_impl_vs_test_conflict(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    conflicts = list(bundle.unresolved_conflicts)
    impl_success = False
    tests_failed = False
    impl_ids: list[str] = []
    test_ids: list[str] = []
    for ev in bundle.evidence:
        val = ev.structured_value or {}
        if ev.evidence_type is EvidenceType.IMPLEMENTATION_RESULT:
            if str(val.get("outcome", "")).lower() in ("success", "passed", "pass"):
                impl_success = True
                impl_ids.append(ev.evidence_id)
        if ev.evidence_type in (
            EvidenceType.TARGETED_TEST_RESULT,
            EvidenceType.FULL_TEST_RESULT,
        ):
            failed = int(val.get("failed_count") or 0)
            if failed > 0 or str(val.get("status", "")).lower() in ("failed", "fail"):
                tests_failed = True
                test_ids.append(ev.evidence_id)
    ti = bundle.test_intelligence or {}
    if int(ti.get("failed_count") or 0) > 0:
        tests_failed = True
    if impl_success and tests_failed:
        conflicts.append(
            {
                "conflict_id": "impl_success_vs_tests_failed",
                "description": (
                    "Implementer reported success but authoritative test evidence shows failures"
                ),
                "preferred_evidence_ids": sorted(test_ids),
                "contradicted_evidence_ids": sorted(impl_ids),
                "resolution": "prioritize_authoritative_test_evidence",
            }
        )
    return conflicts


def _compute_report_status(bundle: EvidenceBundle, conflicts: list[dict[str, Any]]) -> ReportStatus:
    if bundle.workflow_blocked or any("stalemate" in b.lower() or "blocked" in b.lower() for b in bundle.blockers):
        return ReportStatus.BLOCKED
    if conflicts:
        return ReportStatus.CONFLICTING_EVIDENCE
    if bundle.unavailable_mandatory:
        return ReportStatus.INCOMPLETE
    notes = bool(bundle.risks) or bool(bundle.legacy_marks)
    # Non-blocking notes
    blocking_risks = [r for r in bundle.risks if r.blocking]
    if blocking_risks:
        return ReportStatus.INCOMPLETE
    if notes:
        return ReportStatus.COMPLETE_WITH_NOTES
    return ReportStatus.COMPLETE


def _acceptance_summary(rows: list[AcceptanceCriterionRow]) -> str:
    if not rows:
        return "unavailable"
    parts = []
    for st in CriterionStatus:
        n = sum(1 for r in rows if r.status is st)
        if n:
            parts.append(f"{st.value}={n}")
    return ", ".join(parts)


def _ensure_passed_has_evidence(rows: list[AcceptanceCriterionRow]) -> None:
    for row in rows:
        if row.status in (CriterionStatus.PASSED, CriterionStatus.PASSED_WITH_NOTES):
            if not row.evidence_ids:
                raise ReportingBuildError(
                    f"acceptance_passed_without_evidence:{row.criterion_id}"
                )
            if row.claim_status is ClaimStatus.REPORTED:
                # Implementer-only claim cannot mark passed
                raise ReportingBuildError(
                    f"acceptance_passed_on_reported_only:{row.criterion_id}"
                )


def _usage_fields_normalized(fields: list[UsageField]) -> list[UsageField]:
    out: list[UsageField] = []
    for f in sorted(fields, key=lambda x: x.name):
        if f.state in (UsageEvidenceState.UNAVAILABLE, UsageEvidenceState.NOT_APPLICABLE):
            out.append(
                UsageField(
                    name=f.name,
                    state=f.state,
                    value=None,
                    unit=f.unit,
                    method=f.method,
                    assumptions=f.assumptions,
                )
            )
            continue
        if f.state is UsageEvidenceState.ESTIMATED and not f.method:
            raise ReportingBuildError(f"estimated_usage_requires_method:{f.name}")
        if f.name in ("monetary_cost", "cost") and f.value is not None:
            if not f.currency or not f.pricing_source:
                raise ReportingBuildError("monetary_cost_requires_currency_and_pricing_source")
        out.append(f)
    return out


def _default_dependency(dep: dict[str, Any]) -> dict[str, Any]:
    data = dict(dep)
    if "vulnerability_scan" not in data:
        data["vulnerability_scan"] = "unavailable"
    if data.get("vulnerability_scan") == "passed":
        # Policy: never claim passed without vuln DB
        data["vulnerability_scan"] = "unavailable"
        data["vulnerability_scan_note"] = (
            "vulnerability_scan cannot be 'passed' without a queried vulnerability database"
        )
    return data


def _section_payloads(bundle: EvidenceBundle, exec_summary: dict[str, Any]) -> dict[str, dict]:
    git = dict(bundle.git_intelligence)
    tests = dict(bundle.test_intelligence)
    ci = dict(bundle.ci_intelligence)
    dep = _default_dependency(bundle.dependency_intelligence)
    prov = dict(bundle.provider_orchestration)
    if prov and not prov.get("execution_mode"):
        prov["execution_mode"] = "simulation"
    if prov.get("execution_mode") == "simulation":
        prov["simulation_label"] = "simulation (not a live model result)"

    changes = {
        "files_added": list(git.get("files_added") or []),
        "files_modified": list(git.get("files_modified") or []),
        "files_deleted": list(git.get("files_deleted") or []),
        "documentation_only": bundle.documentation_only,
        "categories": list(git.get("file_categories") or []),
    }
    # Executive collapse: counts only
    changes_summary = {
        "added_count": len(changes["files_added"]),
        "modified_count": len(changes["files_modified"]),
        "deleted_count": len(changes["files_deleted"]),
        "documentation_only": bundle.documentation_only,
    }

    sec_conclusion = "Configured checks found no matching issue" if not bundle.security_findings else (
        f"{len(bundle.security_findings)} security finding(s) recorded"
    )
    note = "Clean scan means only that configured checks found no matching issue"
    if not bundle.security_findings and not dep:
        security_payload = {"conclusion": sec_conclusion, "note": note}
    else:
        security_payload = {
            "conclusion": sec_conclusion,
            "findings": [f.to_dict() for f in sorted(bundle.security_findings, key=lambda x: x.finding_id)],
            "dependencies": dep,
            "note": note,
        }

    usage_payload = {}
    if bundle.usage_fields:
        usage_payload = {
            "fields": [u.to_dict() for u in bundle.usage_fields],
        }
    elif any(
        e.evidence_type is EvidenceType.USAGE and e.availability_state is AvailabilityState.UNAVAILABLE
        for e in bundle.evidence
    ):
        usage_payload = {"fields": [{"name": "provider_usage", "state": "unavailable", "value": None}]}

    return {
        "status_glance": {
            "report_status": None,  # filled later
            "outcome": bundle.outcome,
            "final_verdict": bundle.final_verdict,
            "blockers": list(bundle.blockers),
        },
        "executive_summary": exec_summary,
        "objective_scope": {
            "objective": bundle.task_objective,
            "project_id": bundle.project_id,
            "task_id": bundle.task_id,
            "plan_id": bundle.plan_id,
        },
        "outcome": {"outcome": bundle.outcome, "final_verdict": bundle.final_verdict},
        "acceptance": {
            "rows": [r.to_dict() for r in sorted(bundle.acceptance, key=lambda x: x.criterion_id)]
        },
        "changes": changes,
        "changes_summary": changes_summary,
        "validation": {
            "acceptance": _acceptance_summary(bundle.acceptance),
            "review": (bundle.provider_orchestration or {}).get("review_verdict")
            or bundle.final_verdict,
            "tests": tests.get("summary") or "unavailable",
            "ci": ci.get("summary") or ci.get("status") or "unavailable",
        },
        "tests": tests,
        "ci": ci,
        "review": {
            "verdict": (bundle.provider_orchestration or {}).get("review_verdict")
            or bundle.final_verdict,
            "findings": [
                e.structured_value
                for e in sorted(bundle.evidence, key=lambda x: x.evidence_id)
                if e.evidence_type is EvidenceType.REVIEW_FINDING
            ],
        },
        "security_deps": security_payload,
        "failures_repairs": {
            "repairs": list(bundle.repair_history),
            "root_causes": [r.to_dict() for r in bundle.root_causes],
        },
        "provider_orch": prov,
        "usage": usage_payload,
        "risks": {
            "risks": [r.to_dict() for r in sorted(bundle.risks, key=lambda x: x.risk_id)],
            "unresolved_conflicts": list(conflicts_safe(bundle)),
            "blockers": list(bundle.blockers),
        },
        "approvals": {"approvals": list(bundle.approvals)},
        "next_action": {
            "actions": [n.to_dict() for n in sorted(bundle.next_actions, key=lambda x: (x.order, x.action_id))]
        },
        "evidence_summary": {
            "count": len(bundle.evidence),
            "ids": sorted(e.evidence_id for e in bundle.evidence),
        },
        "audit_appendix": {
            "schema_version": REPORT_SCHEMA_VERSION,
            "policy_versions": {
                "report": REPORT_POLICY_VERSION,
                "relevance": RELEVANCE_POLICY_VERSION,
                "redaction": REDACTION_POLICY_VERSION,
                "renderer": RENDERER_VERSION,
            },
            "source_bindings": dict(bundle.source_bindings),
        },
        "operator_state": {
            "task_id": bundle.task_id,
            "project_id": bundle.project_id,
            "orchestration_id": bundle.orchestration_id,
            "provider_mode": (prov.get("execution_mode") or "unknown"),
            "blockers": list(bundle.blockers),
            "approvals": list(bundle.approvals),
        },
    }


def conflicts_safe(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    return list(bundle.unresolved_conflicts)


def build_canonical_report(
    bundle: EvidenceBundle,
    *,
    audience: ReportAudience,
    detail_level: DetailLevel,
    producer_version: str | None = None,
) -> CanonicalReportSnapshot:
    _reject_equitify(
        bundle.project_id,
        bundle.task_id,
        bundle.repository_identity,
        bundle.task_objective,
    )
    evidence = sorted(bundle.evidence, key=lambda e: e.evidence_id)
    for ev in evidence:
        ev.structured_value = sanitize_structure(
            ev.structured_value, field_path=f"evidence.{ev.evidence_id}", events=[]
        )
        if not ev.integrity_hash:
            ev.compute_integrity_hash()
        if producer_version and not ev.producer_version:
            ev.producer_version = producer_version

    claims = sorted(bundle.claims, key=lambda c: c.claim_id)
    _validate_evidence_graph(evidence, claims)
    _ensure_passed_has_evidence(bundle.acceptance)
    bundle.usage_fields = _usage_fields_normalized(bundle.usage_fields)
    bundle.dependency_intelligence = _default_dependency(bundle.dependency_intelligence)

    conflicts = _detect_impl_vs_test_conflict(bundle)
    bundle.unresolved_conflicts = conflicts

    # Mark conflicting claims
    if conflicts:
        for claim in claims:
            if claim.status is ClaimStatus.VERIFIED and "success" in claim.text.lower():
                claim.status = ClaimStatus.CONFLICTING
                claim.notes = (claim.notes or "") + " Marked conflicting due to test evidence"

    # Prefer authoritative evidence when ranking
    evidence = sorted(
        evidence,
        key=lambda e: (-_authority_rank(e.authority_level), e.evidence_id),
    )
    evidence = sorted(evidence, key=lambda e: e.evidence_id)  # stable ID order for manifest

    missing_approval = any(
        a.get("validity") in ("invalid", "stale", "invalidated") for a in bundle.approvals
    ) or (
        "approval" in (m.lower() for m in bundle.unavailable_mandatory)
    )
    failed_ci = str((bundle.ci_intelligence or {}).get("status", "")).lower() in (
        "failed",
        "fail",
        "blocked",
    ) or str((bundle.ci_intelligence or {}).get("conclusion", "")).lower() in (
        "fail",
        "failed",
        "blocked",
    )
    repairs_present = bool(bundle.repair_history)
    usage_relevant = bool(bundle.usage_fields) or any(
        e.evidence_type is EvidenceType.USAGE for e in evidence
    )

    highest_risk = None
    sorted_risks = sorted(
        bundle.risks,
        key=lambda r: (
            0 if r.blocking else 1,
            0 if r.severity is SecuritySeverity.CRITICAL else 1,
            0 if r.severity is SecuritySeverity.HIGH else 2,
            r.risk_id,
        ),
    )
    if sorted_risks:
        highest_risk = f"{sorted_risks[0].severity.value}: {sorted_risks[0].description}"

    required_human = None
    if missing_approval:
        required_human = "Resolve approval validity before proceeding"
    elif bundle.blockers:
        required_human = bundle.blockers[0]
    elif sorted_risks and sorted_risks[0].blocking:
        required_human = f"Address blocking risk {sorted_risks[0].risk_id}"

    next_step = None
    if bundle.next_actions:
        ordered = sorted(bundle.next_actions, key=lambda n: (n.order, n.action_id))
        next_step = ordered[0].text

    tests = bundle.test_intelligence or {}
    test_summary = tests.get("summary")
    if not test_summary:
        if tests.get("not_run"):
            test_summary = "not run"
        elif "passed_count" in tests:
            test_summary = (
                f"passed={tests.get('passed_count')}, failed={tests.get('failed_count', 0)}, "
                f"skipped={tests.get('skipped_count', 0)}"
            )
        else:
            test_summary = "unavailable"

    ci = bundle.ci_intelligence or {}
    ci_summary = ci.get("summary") or ci.get("status") or "unavailable"
    if ci.get("remote_status") == "unavailable":
        ci_summary = f"{ci_summary}; remote_ci=unavailable"

    evidence_completeness = "high"
    if bundle.unavailable_mandatory or conflicts:
        evidence_completeness = "low"
    elif bundle.risks or bundle.legacy_marks:
        evidence_completeness = "medium"

    key_changes = []
    git = bundle.git_intelligence or {}
    for label, key in (
        ("added", "files_added"),
        ("modified", "files_modified"),
        ("deleted", "files_deleted"),
    ):
        files = list(git.get(key) or [])
        if files:
            key_changes.append(f"{label}: {len(files)} file(s)")
    if bundle.documentation_only:
        key_changes.append("documentation-only change")

    repair_status = "none"
    if bundle.repair_history:
        repair_status = f"{len(bundle.repair_history)} repair round(s)"

    redaction_events = []
    # Sanitize free-text fields
    bundle.task_objective = sanitize_structure(
        bundle.task_objective, field_path="task_objective", events=redaction_events
    )
    bundle.outcome = sanitize_structure(
        bundle.outcome, field_path="outcome", events=redaction_events
    )

    exec_summary = build_executive_summary(
        task_objective=bundle.task_objective,
        outcome=bundle.outcome or "unspecified",
        acceptance_summary=_acceptance_summary(bundle.acceptance),
        review_verdict=str(
            (bundle.provider_orchestration or {}).get("review_verdict") or bundle.final_verdict or "unavailable"
        ),
        test_summary=str(test_summary),
        ci_summary=str(ci_summary),
        security_blockers=[
            f"{f.finding_id}:{f.title}" for f in bundle.security_findings if f.blocking
        ]
        + list(bundle.blockers),
        repair_status=repair_status,
        highest_risk=highest_risk,
        required_human_action=required_human,
        next_step=next_step,
        evidence_completeness=evidence_completeness,
        key_changes=key_changes,
    )

    # Temporarily attach conflicts for section payloads
    bundle.unresolved_conflicts = conflicts
    payloads = _section_payloads(bundle, exec_summary)

    report_status = _compute_report_status(bundle, conflicts)
    payloads["status_glance"]["report_status"] = report_status.value

    included_ids, decisions = select_sections(
        audience=audience,
        detail_level=detail_level,
        section_payloads=payloads,
        blockers=bundle.blockers,
        risks=bundle.risks,
        conflicting=bool(conflicts),
        failed_ci=failed_ci,
        missing_approval=bool(missing_approval),
        repairs_present=repairs_present,
        usage_relevant=usage_relevant,
        documentation_only=bundle.documentation_only,
    )

    title_map = {r.section_id: r.title for r in SECTION_RULES}
    section_records: list[SectionRecord] = []
    decision_by_section = {d.section_id: d for d in decisions if d.section_id in included_ids}
    for sid in included_ids:
        content = payloads.get(sid) or {}
        if sid == "changes" and audience is ReportAudience.EXECUTIVE and detail_level is DetailLevel.SUMMARY:
            content = payloads.get("changes_summary") or content
        collapsed = (
            decision_by_section.get(sid) is not None
            and decision_by_section[sid].decision.value == "collapsed"
        )
        section_records.append(
            SectionRecord(
                section_id=sid,
                title=title_map.get(sid, sid),
                content=content,
                included=True,
                collapsed=collapsed,
            )
        )

    bindings = dict(bundle.source_bindings)
    bindings.update(
        {
            "task_id": bundle.task_id,
            "project_id": bundle.project_id,
            "plan_id": bundle.plan_id,
            "orchestration_id": bundle.orchestration_id,
            "starting_commit": bundle.starting_commit,
            "final_commit": bundle.final_commit,
            "task_fingerprint": bindings.get("task_fingerprint"),
            "plan_fingerprint": bindings.get("plan_fingerprint"),
            "approval_fingerprint": bindings.get("approval_fingerprint"),
            "report_policy_version": REPORT_POLICY_VERSION,
            "relevance_policy_version": RELEVANCE_POLICY_VERSION,
            "redaction_policy_version": REDACTION_POLICY_VERSION,
        }
    )
    sfp = source_set_fingerprint(evidence=evidence, bindings=bindings)
    rid = new_report_id(
        source_set_fp=sfp, audience=audience.value, detail=detail_level.value
    )

    ci_run_ids = list((bundle.ci_intelligence or {}).get("run_ids") or [])
    if bundle.ci_intelligence.get("run_id"):
        ci_run_ids.append(str(bundle.ci_intelligence["run_id"]))
    ci_run_ids = sorted(set(ci_run_ids))

    snapshot = CanonicalReportSnapshot(
        report_id=rid,
        schema_version=REPORT_SCHEMA_VERSION,
        report_policy_version=REPORT_POLICY_VERSION,
        relevance_policy_version=RELEVANCE_POLICY_VERSION,
        redaction_policy_version=REDACTION_POLICY_VERSION,
        renderer_version=RENDERER_VERSION,
        generated_at=bundle.generated_at or utc_now_iso(),
        report_status=report_status,
        audience=audience,
        detail_level=detail_level,
        project_id=bundle.project_id,
        task_id=bundle.task_id,
        plan_id=bundle.plan_id,
        orchestration_id=bundle.orchestration_id,
        ci_run_ids=ci_run_ids,
        starting_commit=bundle.starting_commit,
        final_commit=bundle.final_commit,
        repository_identity=bundle.repository_identity,
        task_objective=bundle.task_objective,
        acceptance_criteria=sorted(bundle.acceptance, key=lambda r: r.criterion_id),
        outcome=bundle.outcome,
        final_verdict=bundle.final_verdict,
        section_records=section_records,
        claim_records=claims,
        evidence_manifest=evidence,
        unresolved_conflicts=conflicts,
        unavailable_mandatory=sorted(bundle.unavailable_mandatory),
        approvals=sorted(bundle.approvals, key=lambda a: str(a.get("approval_id") or a.get("type") or "")),
        risks=sorted(bundle.risks, key=lambda r: r.risk_id),
        blockers=list(bundle.blockers),
        next_actions=sorted(bundle.next_actions, key=lambda n: (n.order, n.action_id)),
        root_causes=sorted(bundle.root_causes, key=lambda r: r.root_cause_id),
        security_findings=sorted(bundle.security_findings, key=lambda f: f.finding_id),
        usage_fields=bundle.usage_fields,
        relevance_decisions=decisions,
        redaction_events=redaction_events,
        privacy_classification=PrivacyClassification.INTERNAL,
        retention_classification=RetentionClass.TASK_LIFETIME,
        source_set_fingerprint=sfp,
        source_bindings=bindings,
        ordering_metadata={
            "section_order": included_ids,
            "evidence_order": [e.evidence_id for e in evidence],
        },
        failure_class=(
            ReportingFailureClass.CONFLICTING_MATERIAL
            if conflicts
            else ReportingFailureClass.MISSING_MANDATORY_EVIDENCE
            if bundle.unavailable_mandatory
            else ReportingFailureClass.BLOCKED_WORKFLOW
            if report_status is ReportStatus.BLOCKED
            else ReportingFailureClass.NONE
        ),
        executive_summary=exec_summary,
        git_intelligence=dict(bundle.git_intelligence),
        test_intelligence=dict(bundle.test_intelligence),
        ci_intelligence=dict(bundle.ci_intelligence),
        dependency_intelligence=dict(bundle.dependency_intelligence),
        provider_orchestration=dict(bundle.provider_orchestration),
        repair_history=list(bundle.repair_history),
        documentation_only=bundle.documentation_only,
        legacy_marks=list(bundle.legacy_marks),
    )
    snapshot.report_fingerprint = compute_report_fingerprint(snapshot)
    return snapshot
