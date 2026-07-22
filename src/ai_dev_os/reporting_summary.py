"""Deterministic executive summary templates (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from .reporting_constants import BANNED_EXECUTIVE_PHRASES


def _scrub(text: str) -> str:
    out = text
    for phrase in BANNED_EXECUTIVE_PHRASES:
        out = re.sub(re.escape(phrase), "[policy-blocked phrase]", out, flags=re.IGNORECASE)
    return out


def build_executive_summary(
    *,
    task_objective: str,
    outcome: str,
    acceptance_summary: str,
    review_verdict: str,
    test_summary: str,
    ci_summary: str,
    security_blockers: list[str],
    repair_status: str,
    highest_risk: str | None,
    required_human_action: str | None,
    next_step: str | None,
    evidence_completeness: str,
    key_changes: list[str],
) -> dict[str, Any]:
    blockers = list(security_blockers)
    paragraph = (
        f"Requested: {_scrub(task_objective)}. Outcome: {_scrub(outcome)}. "
        f"Acceptance: {_scrub(acceptance_summary)}. Review: {_scrub(review_verdict)}. "
        f"Tests: {_scrub(test_summary)}. CI: {_scrub(ci_summary)}. "
        f"Repairs: {_scrub(repair_status)}."
    )
    if blockers:
        paragraph += " Blockers remain: " + "; ".join(_scrub(b) for b in blockers[:5]) + "."

    return {
        "overall_outcome": _scrub(outcome),
        "completion_confidence": evidence_completeness,
        "result_paragraph": paragraph,
        "key_changes": [_scrub(c) for c in key_changes[:8]],
        "validation_summary": (
            f"Acceptance={acceptance_summary}; review={review_verdict}; "
            f"tests={test_summary}; CI={ci_summary}"
        ),
        "highest_remaining_risk": _scrub(highest_risk) if highest_risk else "None identified",
        "required_human_action": _scrub(required_human_action)
        if required_human_action
        else "None required",
        "next_recommended_step": _scrub(next_step) if next_step else "No further action recorded",
        "security_blockers": [_scrub(b) for b in blockers],
    }
