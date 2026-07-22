"""Deterministic progress and stalemate detection (no LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fingerprints import fingerprint
from .orchestration_config import OrchestrationConfig
from .orchestration_models import (
    OrchestrationFailureClass,
    ProgressStatus,
    RoundEvidence,
    StalemateStatus,
    findings_fingerprint,
)


@dataclass
class StalemateDecision:
    stalemate: bool
    failure_class: OrchestrationFailureClass
    reason: str
    progress_status: ProgressStatus
    evidence: dict[str, Any]


def compute_progress_state_fingerprint(evidence: RoundEvidence) -> str:
    payload = {
        "diff": evidence.worktree_diff_fingerprint,
        "failing_tests": evidence.failing_test_fingerprint,
        "findings": evidence.review_findings_fingerprint
        or findings_fingerprint(evidence.canonical_findings),
        "verdict": evidence.review_verdict,
    }
    if not payload["diff"] and not payload["failing_tests"] and not payload["findings"]:
        # Missing core evidence — fingerprint still computed but caller fail-closes.
        payload["missing_core"] = True
    return fingerprint(payload)


def _identical_evidence(a: RoundEvidence, b: RoundEvidence) -> bool:
    return (
        (a.worktree_diff_fingerprint or "") == (b.worktree_diff_fingerprint or "")
        and (a.failing_test_fingerprint or "") == (b.failing_test_fingerprint or "")
        and (a.review_findings_fingerprint or "") == (b.review_findings_fingerprint or "")
        and (a.review_verdict or "") == (b.review_verdict or "")
    )


def evaluate_round_progress(
    current: RoundEvidence,
    previous: RoundEvidence | None,
    *,
    require_evidence: bool = True,
) -> StalemateDecision:
    """Compare current round to previous; fail closed if evidence missing."""
    missing = []
    if require_evidence:
        if not current.worktree_diff_fingerprint:
            missing.append("worktree_diff_fingerprint")
        if current.review_verdict and not current.review_findings_fingerprint:
            # Allow empty findings with explicit fingerprint of empty list.
            if current.canonical_findings is None:
                missing.append("review_findings_fingerprint")
        if current.test_execution_result_id and not current.failing_test_fingerprint:
            # Empty failing set still needs fingerprint.
            missing.append("failing_test_fingerprint")
    if missing:
        return StalemateDecision(
            stalemate=True,
            failure_class=OrchestrationFailureClass.NO_PROGRESS,
            reason=f"Missing required progress evidence: {', '.join(missing)}",
            progress_status=ProgressStatus.INDETERMINATE,
            evidence={"missing": missing},
        )

    if previous is None:
        return StalemateDecision(
            stalemate=False,
            failure_class=OrchestrationFailureClass.NONE,
            reason="first round",
            progress_status=ProgressStatus.PROGRESS,
            evidence={"first_round": True},
        )

    # Progress signals (meaningful — not cosmetic-only diffs)
    diff_changed = (current.worktree_diff_fingerprint or "") != (
        previous.worktree_diff_fingerprint or ""
    )
    prev_fail = set(previous.failing_test_identifiers or [])
    cur_fail = set(current.failing_test_identifiers or [])
    failing_shrunk = len(cur_fail) < len(prev_fail) or (
        bool(prev_fail) and cur_fail < prev_fail
    )
    prev_findings = {f.finding_id for f in previous.canonical_findings}
    cur_findings = {f.finding_id for f in current.canonical_findings}
    findings_resolved = bool(prev_findings - cur_findings)
    verdict_improved = (previous.review_verdict == "changes_required") and (
        current.review_verdict in ("pass", "pass_with_notes")
    )
    findings_identical = (current.review_findings_fingerprint or "") == (
        previous.review_findings_fingerprint or ""
    )
    failing_identical = (current.failing_test_fingerprint or "") == (
        previous.failing_test_fingerprint or ""
    )
    verdict_same = (current.review_verdict or "") == (previous.review_verdict or "")

    meaningful = failing_shrunk or findings_resolved or verdict_improved
    if meaningful:
        return StalemateDecision(
            stalemate=False,
            failure_class=OrchestrationFailureClass.NONE,
            reason="progress detected",
            progress_status=ProgressStatus.PROGRESS,
            evidence={
                "diff_changed": diff_changed,
                "failing_shrunk": failing_shrunk,
                "findings_resolved": findings_resolved,
                "verdict_improved": verdict_improved,
            },
        )

    # No meaningful improvement (cosmetic diffs alone do not count)
    if findings_identical and failing_identical and verdict_same:
        return StalemateDecision(
            stalemate=False,
            failure_class=OrchestrationFailureClass.NO_PROGRESS,
            reason="no_change_repair",
            progress_status=ProgressStatus.NO_PROGRESS,
            evidence={
                "identical_to_previous": _identical_evidence(current, previous),
                "diff_changed_without_improvement": diff_changed,
                "files_changed_count": len(current.files_changed or []),
            },
        )

    return StalemateDecision(
        stalemate=False,
        failure_class=OrchestrationFailureClass.NONE,
        reason="indeterminate",
        progress_status=ProgressStatus.INDETERMINATE,
        evidence={"diff_changed": diff_changed},
    )


def detect_stalemate(
    rounds: list[RoundEvidence],
    *,
    history: list[str],
    consecutive_no_progress: int,
    consecutive_malformed: int,
    config: OrchestrationConfig,
) -> StalemateDecision:
    """Authoritative stalemate rules A–D."""
    # D: repeated malformed
    if consecutive_malformed >= config.consecutive_no_progress_threshold:
        return StalemateDecision(
            stalemate=True,
            failure_class=OrchestrationFailureClass.MALFORMED_PROVIDER_RESULT,
            reason="Repeated malformed or unusable provider output",
            progress_status=ProgressStatus.NO_PROGRESS,
            evidence={"consecutive_malformed": consecutive_malformed},
        )

    # A: exact consecutive identical evidence
    if len(rounds) >= config.consecutive_no_progress_threshold:
        window = rounds[-config.consecutive_no_progress_threshold :]
        if all(_identical_evidence(window[0], r) for r in window[1:]):
            return StalemateDecision(
                stalemate=True,
                failure_class=OrchestrationFailureClass.NO_PROGRESS,
                reason="Exact consecutive stalemate: identical diff/tests/findings/verdict",
                progress_status=ProgressStatus.NO_PROGRESS,
                evidence={
                    "kind": "exact_consecutive",
                    "threshold": config.consecutive_no_progress_threshold,
                    "progress_state_fingerprint": window[-1].progress_state_fingerprint,
                },
            )

    # B: consecutive no-progress counter
    if consecutive_no_progress >= config.consecutive_no_progress_threshold:
        return StalemateDecision(
            stalemate=True,
            failure_class=OrchestrationFailureClass.NO_PROGRESS,
            reason="No-change repair threshold reached",
            progress_status=ProgressStatus.NO_PROGRESS,
            evidence={
                "kind": "no_change_repair",
                "consecutive_no_progress": consecutive_no_progress,
            },
        )

    # C: oscillation A-B-A
    hist = history[-config.oscillation_history_window :]
    if len(hist) >= 3:
        for i in range(len(hist) - 2):
            a, b, c = hist[i], hist[i + 1], hist[i + 2]
            if a == c and a != b:
                return StalemateDecision(
                    stalemate=True,
                    failure_class=OrchestrationFailureClass.OSCILLATION_DETECTED,
                    reason="Oscillation detected (A-B-A progress-state fingerprint)",
                    progress_status=ProgressStatus.NO_PROGRESS,
                    evidence={
                        "kind": "oscillation",
                        "pattern": [a[:12], b[:12], c[:12]],
                        StalemateStatus.DETECTED.value: True,
                    },
                )

    return StalemateDecision(
        stalemate=False,
        failure_class=OrchestrationFailureClass.NONE,
        reason="no stalemate",
        progress_status=ProgressStatus.UNKNOWN,
        evidence={},
    )
