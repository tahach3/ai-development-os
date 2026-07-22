"""Deterministic relevance engine (no LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .reporting_models import (
    DetailLevel,
    RelevanceDecision,
    RelevanceDecisionKind,
    ReportAudience,
    RiskRecord,
    SecuritySeverity,
)


@dataclass(frozen=True)
class SectionRule:
    section_id: str
    title: str
    order: int
    audiences: frozenset[ReportAudience]
    detail_levels: frozenset[DetailLevel]
    rule_id: str
    always_if_blocker: bool = False
    omit_if_empty: bool = True
    collapse_for: frozenset[ReportAudience] = frozenset()


SECTION_RULES: tuple[SectionRule, ...] = (
    SectionRule(
        "status_glance",
        "Status at a glance",
        10,
        frozenset(ReportAudience),
        frozenset(DetailLevel),
        "rel.status_glance",
        omit_if_empty=False,
    ),
    SectionRule(
        "executive_summary",
        "Executive summary",
        20,
        frozenset(
            {
                ReportAudience.EXECUTIVE,
                ReportAudience.OPERATOR,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
            }
        ),
        frozenset(DetailLevel),
        "rel.executive_summary",
        omit_if_empty=False,
    ),
    SectionRule(
        "objective_scope",
        "Objective and scope",
        30,
        frozenset(ReportAudience),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.objective_scope",
    ),
    SectionRule(
        "outcome",
        "Outcome",
        40,
        frozenset(ReportAudience),
        frozenset(DetailLevel),
        "rel.outcome",
        omit_if_empty=False,
    ),
    SectionRule(
        "acceptance",
        "Acceptance-criteria results",
        50,
        frozenset(
            {
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
                ReportAudience.OPERATOR,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.acceptance",
    ),
    SectionRule(
        "changes",
        "Changes made",
        60,
        frozenset(
            {
                ReportAudience.EXECUTIVE,
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
            }
        ),
        frozenset(DetailLevel),
        "rel.changes",
        collapse_for=frozenset({ReportAudience.EXECUTIVE}),
    ),
    SectionRule(
        "validation",
        "Validation",
        70,
        frozenset(ReportAudience),
        frozenset(DetailLevel),
        "rel.validation",
        omit_if_empty=False,
    ),
    SectionRule(
        "tests",
        "Tests",
        80,
        frozenset(
            {
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
                ReportAudience.OPERATOR,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.tests",
    ),
    SectionRule(
        "ci",
        "CI",
        90,
        frozenset(
            {
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
                ReportAudience.OPERATOR,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.ci",
    ),
    SectionRule(
        "review",
        "Review findings",
        100,
        frozenset(
            {
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.review",
    ),
    SectionRule(
        "security_deps",
        "Security and dependencies",
        110,
        frozenset(
            {
                ReportAudience.EXECUTIVE,
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
            }
        ),
        frozenset(DetailLevel),
        "rel.security_deps",
        always_if_blocker=True,
        collapse_for=frozenset({ReportAudience.EXECUTIVE}),
    ),
    SectionRule(
        "failures_repairs",
        "Failures and repairs",
        120,
        frozenset(
            {
                ReportAudience.DEVELOPER,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
                ReportAudience.OPERATOR,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.failures_repairs",
    ),
    SectionRule(
        "provider_orch",
        "Provider and orchestration activity",
        130,
        frozenset(
            {
                ReportAudience.OPERATOR,
                ReportAudience.DEVELOPER,
                ReportAudience.AUDITOR,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.provider_orch",
    ),
    SectionRule(
        "usage",
        "Usage and performance",
        140,
        frozenset(
            {
                ReportAudience.OPERATOR,
                ReportAudience.DEVELOPER,
                ReportAudience.AUDITOR,
                ReportAudience.EXECUTIVE,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.usage",
    ),
    SectionRule(
        "risks",
        "Risks and unresolved issues",
        150,
        frozenset(ReportAudience),
        frozenset(DetailLevel),
        "rel.risks",
        always_if_blocker=True,
        omit_if_empty=False,
    ),
    SectionRule(
        "approvals",
        "Human approvals and decisions",
        160,
        frozenset(
            {
                ReportAudience.OPERATOR,
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
                ReportAudience.EXECUTIVE,
            }
        ),
        frozenset({DetailLevel.STANDARD, DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.approvals",
    ),
    SectionRule(
        "next_action",
        "Recommended next action",
        170,
        frozenset(ReportAudience),
        frozenset(DetailLevel),
        "rel.next_action",
        omit_if_empty=False,
    ),
    SectionRule(
        "evidence_summary",
        "Evidence summary",
        180,
        frozenset(
            {
                ReportAudience.INDEPENDENT_REVIEWER,
                ReportAudience.AUDITOR,
                ReportAudience.DEVELOPER,
            }
        ),
        frozenset({DetailLevel.FULL, DetailLevel.AUDIT}),
        "rel.evidence_summary",
    ),
    SectionRule(
        "audit_appendix",
        "Audit appendix",
        190,
        frozenset({ReportAudience.AUDITOR}),
        frozenset({DetailLevel.AUDIT, DetailLevel.FULL}),
        "rel.audit_appendix",
        omit_if_empty=False,
    ),
    SectionRule(
        "operator_state",
        "Operator state",
        25,
        frozenset({ReportAudience.OPERATOR}),
        frozenset(DetailLevel),
        "rel.operator_state",
        omit_if_empty=False,
    ),
)


def _has_critical_blockers(
    blockers: Iterable[str],
    risks: Iterable[RiskRecord],
    *,
    conflicting: bool,
    failed_ci: bool,
    missing_approval: bool,
) -> bool:
    if conflicting or failed_ci or missing_approval:
        return True
    if any(True for _ in blockers):
        return True
    for risk in risks:
        if risk.blocking or risk.severity in (SecuritySeverity.CRITICAL, SecuritySeverity.HIGH):
            return True
    return False


def select_sections(
    *,
    audience: ReportAudience,
    detail_level: DetailLevel,
    section_payloads: dict[str, dict],
    blockers: list[str],
    risks: list[RiskRecord],
    conflicting: bool = False,
    failed_ci: bool = False,
    missing_approval: bool = False,
    repairs_present: bool = False,
    usage_relevant: bool = False,
    documentation_only: bool = False,
) -> tuple[list[str], list[RelevanceDecision]]:
    """Return ordered included section IDs and decision log."""
    critical = _has_critical_blockers(
        blockers, risks, conflicting=conflicting, failed_ci=failed_ci, missing_approval=missing_approval
    )
    decisions: list[RelevanceDecision] = []
    included: list[str] = []

    for rule in sorted(SECTION_RULES, key=lambda r: r.order):
        payload = section_payloads.get(rule.section_id) or {}
        empty = not payload

        if audience not in rule.audiences or detail_level not in rule.detail_levels:
            # Force critical sections regardless of audience/detail (except audit-only appendix).
            if rule.always_if_blocker and critical and rule.section_id in (
                "risks",
                "security_deps",
                "outcome",
                "status_glance",
                "next_action",
            ):
                pass
            elif rule.section_id in ("risks", "next_action", "outcome", "status_glance") and critical:
                pass
            else:
                decisions.append(
                    RelevanceDecision(
                        section_id=rule.section_id,
                        decision=RelevanceDecisionKind.EXCLUDED,
                        rule_id=rule.rule_id,
                        reason="Audience or detail level not applicable",
                        priority=rule.order,
                    )
                )
                continue

        if rule.section_id == "failures_repairs" and not repairs_present and detail_level != DetailLevel.AUDIT:
            decisions.append(
                RelevanceDecision(
                    section_id=rule.section_id,
                    decision=RelevanceDecisionKind.EXCLUDED,
                    rule_id=rule.rule_id + ".no_repair",
                    reason="No repair rounds occurred",
                    priority=rule.order,
                )
            )
            continue

        if rule.section_id == "usage" and not usage_relevant and detail_level != DetailLevel.AUDIT:
            decisions.append(
                RelevanceDecision(
                    section_id=rule.section_id,
                    decision=RelevanceDecisionKind.EXCLUDED,
                    rule_id=rule.rule_id + ".usage_irrelevant",
                    reason="Usage not relevant or unavailable; omit outside audit",
                    priority=rule.order,
                )
            )
            continue

        if (
            documentation_only
            and rule.section_id in ("provider_orch", "failures_repairs")
            and detail_level != DetailLevel.AUDIT
        ):
            decisions.append(
                RelevanceDecision(
                    section_id=rule.section_id,
                    decision=RelevanceDecisionKind.EXCLUDED,
                    rule_id=rule.rule_id + ".docs_only",
                    reason="Documentation-only change; implementation sections shortened/omitted",
                    priority=rule.order,
                )
            )
            continue

        if empty and rule.omit_if_empty and not (rule.always_if_blocker and critical):
            decisions.append(
                RelevanceDecision(
                    section_id=rule.section_id,
                    decision=RelevanceDecisionKind.EXCLUDED,
                    rule_id=rule.rule_id + ".empty",
                    reason="Empty section omitted",
                    priority=rule.order,
                )
            )
            continue

        if audience in rule.collapse_for and detail_level == DetailLevel.SUMMARY:
            decisions.append(
                RelevanceDecision(
                    section_id=rule.section_id,
                    decision=RelevanceDecisionKind.COLLAPSED,
                    rule_id=rule.rule_id + ".collapse",
                    reason="Collapsed for audience summary",
                    priority=rule.order,
                )
            )
            included.append(rule.section_id)
            continue

        decisions.append(
            RelevanceDecision(
                section_id=rule.section_id,
                decision=RelevanceDecisionKind.INCLUDED,
                rule_id=rule.rule_id,
                reason="Included by relevance policy",
                priority=rule.order,
            )
        )
        included.append(rule.section_id)

    # Critical blockers must always appear even in executive summary.
    for mandatory in ("risks", "next_action", "outcome", "status_glance"):
        if critical and mandatory not in included:
            included.append(mandatory)
            decisions.append(
                RelevanceDecision(
                    section_id=mandatory,
                    decision=RelevanceDecisionKind.INCLUDED,
                    rule_id="rel.mandatory_blocker",
                    reason="Critical blocker/risk forces inclusion",
                    priority=0,
                )
            )

    # Stable unique order by SECTION_RULES order
    order_map = {r.section_id: r.order for r in SECTION_RULES}
    included = sorted(dict.fromkeys(included), key=lambda s: order_map.get(s, 999))
    decisions = sorted(decisions, key=lambda d: (d.priority, d.section_id, d.rule_id))
    return included, decisions
