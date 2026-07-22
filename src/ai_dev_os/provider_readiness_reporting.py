"""Round 4C reporting integration for provider readiness (Round 4D1)."""

from __future__ import annotations

from uuid import uuid4

from .provider_readiness_models import ReadinessAuditBundle
from .reporting_models import (
    AuthorityLevel,
    ClaimRecord,
    ClaimStatus,
    EvidenceItem,
    EvidenceType,
    FreshnessStatus,
)


def readiness_evidence_items(bundle: ReadinessAuditBundle) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for rec in bundle.provider_records:
        item = EvidenceItem(
            evidence_id=f"ev_prdy_{uuid4().hex[:12]}",
            evidence_type=EvidenceType.PROVIDER_READINESS,
            source_type="provider_readiness_audit",
            source_record_type="provider_readiness_record",
            source_record_id=rec.readiness_id,
            structured_value={
                "provider_id": rec.provider_id,
                "final_readiness_verdict": rec.final_readiness_verdict,
                "discovery_status": rec.discovery_status,
                "authentication_status": rec.authentication_status,
                "auth_status_command_advertised": rec.auth_status_command_advertised,
                "noninteractive_status": rec.noninteractive_status,
                "noninteractive_contract": dict(rec.noninteractive_contract or {}),
                "compatibility_status": rec.compatibility_status,
                "implementer_eligibility": rec.implementer_eligibility,
                "reviewer_eligibility": rec.reviewer_eligibility,
                "executable_fingerprint": rec.executable_fingerprint,
                "cli_version": rec.cli_version,
                "blockers": list(rec.blockers),
                "live_provider_invocations": 0,
                "readiness_policy_version": rec.readiness_policy_version,
                "record_fingerprint": rec.record_fingerprint,
                "probes_sanitized": [
                    {
                        "kind": p.get("kind"),
                        "command_identity": p.get("command_identity"),
                        "exit_code": p.get("exit_code"),
                        "parse_status": p.get("parse_status"),
                        "failure_class": p.get("failure_class"),
                        "skipped": p.get("skipped"),
                        "sanitized_output_summary": p.get("sanitized_output_summary"),
                    }
                    for p in (rec.probes or [])
                ],
            },
            safe_summary=(
                f"verdict={rec.final_readiness_verdict}; "
                f"discovery={rec.discovery_status}; "
                f"auth={rec.authentication_status}; "
                f"noninteractive={rec.noninteractive_status}; "
                f"live_invocations=0"
            ),
            authority_level=AuthorityLevel.DETERMINISTIC_DERIVED,
            verification_status=ClaimStatus.VERIFIED,
            freshness_status=FreshnessStatus.FRESH,
            verification_method="deterministic_readiness_policy",
            source_fingerprint=rec.record_fingerprint,
            source_commit=rec.repository_commit,
        )
        item.compute_integrity_hash()
        items.append(item)

    live = EvidenceItem(
        evidence_id=f"ev_prdy_live_{uuid4().hex[:12]}",
        evidence_type=EvidenceType.SECURITY_POLICY_DECISION,
        source_type="provider_readiness_audit",
        source_record_type="readiness_audit_bundle",
        source_record_id=bundle.audit_id,
        structured_value={
            "live_provider_invocations": 0,
            "aggregate_verdict": bundle.aggregate_verdict,
            "host_system_verdict": bundle.host_system_verdict,
            "audit_id": bundle.audit_id,
        },
        safe_summary=(
            f"live_provider_invocations=0; host_system_verdict={bundle.host_system_verdict}; "
            "no model prompts executed"
        ),
        authority_level=AuthorityLevel.AUTHORITATIVE_PERSISTED,
        verification_status=ClaimStatus.VERIFIED,
        freshness_status=FreshnessStatus.FRESH,
        verification_method="invocation_counter",
        source_fingerprint=bundle.record_fingerprint,
    )
    live.compute_integrity_hash()
    items.append(live)
    return items


def readiness_claims(bundle: ReadinessAuditBundle) -> list[ClaimRecord]:
    claims = [
        ClaimRecord(
            claim_id="readiness_aggregate",
            text=f"Aggregate readiness verdict: {bundle.aggregate_verdict}",
            status=ClaimStatus.VERIFIED,
            evidence_ids=[bundle.audit_id],
        ),
        ClaimRecord(
            claim_id="no_live_invocations",
            text="No live provider model invocations occurred during Round 4D1 readiness",
            status=ClaimStatus.VERIFIED,
            evidence_ids=[bundle.audit_id],
        ),
    ]
    if bundle.recommended_combination:
        c = bundle.recommended_combination
        claims.append(
            ClaimRecord(
                claim_id="recommended_combination",
                text=(
                    f"Recommended combination: implementer={c.implementer_provider_id} "
                    f"reviewer={c.reviewer_provider_id} ({c.independence_status})"
                ),
                status=ClaimStatus.REPORTED,
                evidence_ids=[bundle.audit_id],
            )
        )
    return claims


def render_executive_markdown(bundle: ReadinessAuditBundle) -> str:
    combo = bundle.recommended_combination
    combo_line = "none"
    if combo:
        combo_line = (
            f"{combo.implementer_provider_id or 'n/a'} implementer + "
            f"{combo.reviewer_provider_id or 'deterministic/none'} reviewer "
            f"({combo.independence_status})"
        )
    top_blocker = bundle.blockers[0] if bundle.blockers else "none"
    smoke_ready = bundle.aggregate_verdict in (
        "eligible_for_bounded_live_smoke",
        "conditionally_eligible_for_bounded_live_smoke",
    )
    ambiguity_notes = []
    selection_needed = False
    recommended_cand = None
    for r in bundle.provider_records:
        amb = (r.metadata or {}).get("ambiguity_resolution") or {}
        if amb.get("resolved"):
            ambiguity_notes.append(
                f"{r.provider_id}: resolved via {amb.get('collapse_rule_id') or 'rule'}"
            )
        if amb.get("requires_operator_selection"):
            selection_needed = True
            decision = (r.metadata or {}).get("operator_decision") or {}
            recommended_cand = decision.get("recommended_candidate_id")
            ambiguity_notes.append(f"{r.provider_id}: operator_selection_required")
    return "\n".join(
        [
            "# Provider Readiness — Executive Summary",
            "",
            f"- Bounded live smoke ready: {'conditional/yes' if smoke_ready else 'no'} ({bundle.aggregate_verdict})",
            f"- Host system verdict: `{bundle.host_system_verdict}`",
            f"- Ambiguity resolved: {'yes' if ambiguity_notes and not selection_needed else ('partial/no' if ambiguity_notes else 'n/a')}",
            f"- Human executable selection required: {'yes' if selection_needed else 'no'}",
            f"- Recommended candidate: {recommended_cand or 'n/a'}",
            f"- Recommended provider combination: {combo_line}",
            f"- Highest blocker: {top_blocker}",
            "- Required human action: separate Round 4D2 authorization before any live prompt",
            "- Model requests during this audit: 0",
            f"- live_provider_invocations: {bundle.live_provider_invocations}",
            "",
        ]
    )


def render_operator_markdown(bundle: ReadinessAuditBundle) -> str:
    lines = [
        "# Provider Readiness — Operator Report",
        "",
        f"Aggregate verdict: `{bundle.aggregate_verdict}`",
        f"Host system verdict: `{bundle.host_system_verdict}`",
        "",
        "## Providers",
    ]
    for r in bundle.provider_records:
        lines.append(
            f"- **{r.provider_id}**: {r.final_readiness_verdict} "
            f"(discovery={r.discovery_status}, auth={r.authentication_status}, "
            f"noninteractive={r.noninteractive_status}, "
            f"auth_advertised={r.auth_status_command_advertised})"
        )
        for b in r.blockers:
            lines.append(f"  - blocker: {b}")
        amb = (r.metadata or {}).get("ambiguity_resolution") or {}
        if amb.get("candidates"):
            lines.append("  - candidate matrix:")
            for c in amb["candidates"]:
                lines.append(
                    f"    - {c.get('candidate_id')}: {c.get('sanitized_location')} "
                    f"fp={c.get('fingerprint_prefix')} trust={c.get('trust_status')} "
                    f"class={c.get('classification')}"
                )
        decision = (r.metadata or {}).get("operator_decision")
        if decision:
            lines.append(f"  - approval phrase: `{decision.get('approval_phrase')}`")
            lines.append(
                f"  - recommended candidate: {decision.get('recommended_candidate_id')}"
            )
        pin = (r.metadata or {}).get("executable_pin")
        if pin:
            lines.append(f"  - pin status: {pin.get('status')} valid={pin.get('valid')}")
    lines.extend(["", "## Next actions", ""])
    if any(
        ((r.metadata or {}).get("ambiguity_resolution") or {}).get(
            "requires_operator_selection"
        )
        for r in bundle.provider_records
    ):
        lines.append(
            "- Approve one candidate with the exact approval phrase, then `--write-pin` (host-local only)."
        )
    elif bundle.aggregate_verdict == "no_eligible_provider":
        lines.append(
            "- Install/configure an adapter-supported CLI, or wait for 4D2 auth after eligibility."
        )
    elif any("authentication" in b for b in bundle.blockers):
        lines.append(
            "- Do not run login from this tool; authenticate out-of-band, then re-audit."
        )
    else:
        lines.append(
            "- Review blockers; obtain explicit Round 4D2 authorization before live smoke."
        )
    lines.append("- Do not enable live mode from readiness tooling.")
    lines.append("- Local executable pins do not enable live mode and do not imply authentication.")
    lines.append("")
    return "\n".join(lines)


def render_developer_markdown(bundle: ReadinessAuditBundle) -> str:
    lines = [
        "# Provider Readiness — Developer Report",
        "",
        f"Policy version: `{bundle.readiness_policy_version}`",
        f"Schema version: `{bundle.schema_version}`",
        f"Commit: `{bundle.repository_commit}`",
        "",
    ]
    for r in bundle.provider_records:
        amb = (r.metadata or {}).get("ambiguity_resolution") or {}
        lines.extend(
            [
                f"## {r.provider_id}",
                f"- adapter: {r.adapter_id} @ {r.adapter_version}",
                f"- executable: {r.executable_name} ({r.sanitized_executable_location})",
                f"- fingerprint: {r.executable_fingerprint}",
                f"- CLI version: {r.cli_version} ({r.compatibility_status})",
                f"- discovery rule: {r.selected_executable_rule}",
                f"- ambiguity resolved: {amb.get('resolved')} rule={amb.get('collapse_rule_id')}",
                f"- logical installations: {len(amb.get('logical_installations') or [])}",
                f"- roles: implementer={r.implementer_eligibility}, reviewer={r.reviewer_eligibility}",
                f"- independence: {r.reviewer_independence_status}",
                f"- worktree: {r.isolated_worktree_compatibility}",
                f"- structured_output: {r.structured_output_status}",
                f"- timeout/cancel/bounds: {r.timeout_support}/{r.cancellation_support}/{r.output_bounding_support}",
                f"- live_policy: {r.live_policy_status}",
                f"- suggested 4D2 role: {r.recommended_round_4d2_role}",
                f"- restrictions: {', '.join(r.recommended_smoke_test_restrictions)}",
                "",
            ]
        )
        if amb.get("logical_installations"):
            lines.append("Logical installations:")
            for li in amb["logical_installations"]:
                lines.append(
                    f"- {li.get('logical_installation_id')}: "
                    f"status={li.get('ambiguity_status')} "
                    f"rule={li.get('collapse_rule_id')} "
                    f"members={li.get('candidate_ids')}"
                )
            lines.append("")
        lines.append("Role matrix:")
        for m in r.role_matrix:
            lines.append(
                f"- {m.get('role')}: {m.get('eligibility')} "
                f"(adapter={m.get('adapter_supported')}, auth={m.get('authentication_ready')}, "
                f"ni={m.get('noninteractive_ready')})"
            )
        lines.append("")
    lines.append("## Combinations")
    for c in bundle.combinations:
        marker = " (recommended)" if c.recommended else ""
        lines.append(
            f"- {c.category}: {c.implementer_provider_id} / {c.reviewer_provider_id} "
            f"[{c.independence_status}]{marker} — {c.notes}"
        )
    lines.append("")
    lines.append(
        "Notes: PATH precedence alone is not trust; matching versions do not prove executable equivalence."
    )
    lines.append("")
    return "\n".join(lines)


def render_auditor_markdown(bundle: ReadinessAuditBundle) -> str:
    lines = [
        "# Provider Readiness — Auditor Report",
        "",
        f"- audit_id: `{bundle.audit_id}`",
        f"- record_fingerprint: `{bundle.record_fingerprint}`",
        f"- readiness_policy_version: `{bundle.readiness_policy_version}`",
        f"- live_provider_invocations: `{bundle.live_provider_invocations}`",
        "- proof: readiness engine never sends provider prompts; probes allowlisted only",
        "- proof: wrapper contents treated as data; never executed",
        "- proof: path-only pins rejected; fingerprint required",
        "",
    ]
    for r in bundle.provider_records:
        amb = (r.metadata or {}).get("ambiguity_resolution") or {}
        lines.extend(
            [
                f"## {r.provider_id}",
                f"- readiness_id: {r.readiness_id}",
                f"- record_fingerprint: {r.record_fingerprint}",
                f"- executable_fingerprint: {r.executable_fingerprint}",
                f"- ambiguity schema: {amb.get('schema_version')}",
                f"- collapse rule: {amb.get('collapse_rule_id')}",
                "- redactions: tokens redacted from probe summaries; full PATH not recorded",
                "",
                "### Sanitized candidates",
            ]
        )
        for c in amb.get("candidates") or []:
            lines.append(
                f"- {c.get('candidate_id')}: kind={c.get('file_kind')} "
                f"fp={c.get('fingerprint_prefix')} class={c.get('classification')} "
                f"trust={c.get('trust_status')} wrapper={c.get('wrapper_type')}"
            )
        lines.append("")
        lines.append("### Sanitized probes")
        for p in r.probes:
            lines.append(
                f"- {p.get('kind')}: cmd=`{p.get('command_identity')}` exit={p.get('exit_code')} "
                f"failure={p.get('failure_class')} skipped={p.get('skipped')} "
                f"summary={p.get('sanitized_output_summary')}"
            )
        lines.append("")
        lines.append("### Audit events")
        for e in r.audit_events:
            lines.append(f"- {e.get('event_type')}: {e.get('message')}")
        pin = (r.metadata or {}).get("executable_pin")
        if pin:
            lines.append(f"- pin integrity: valid={pin.get('valid')} status={pin.get('status')}")
        lines.append("")
    return "\n".join(lines)


def render_all_audiences(bundle: ReadinessAuditBundle) -> dict[str, str]:
    return {
        "executive": render_executive_markdown(bundle),
        "operator": render_operator_markdown(bundle),
        "developer": render_developer_markdown(bundle),
        "auditor": render_auditor_markdown(bundle),
    }


def human_summary(bundle: ReadinessAuditBundle) -> str:
    return render_executive_markdown(bundle)
