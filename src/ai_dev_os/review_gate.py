"""Review verdict gate rules."""

from __future__ import annotations

from .models import FindingSeverity, ReviewReport, ReviewVerdict, Task, TaskStatus
from .validation import ValidationError, apply_status_transition


BLOCKING_SEVERITIES = frozenset({FindingSeverity.BLOCKER, FindingSeverity.MAJOR})


def unresolved_blocking_findings(report: ReviewReport) -> list:
    """Confirmed (or general) findings that block pass_with_notes progression."""
    pool = report.confirmed_findings or report.findings
    return [f for f in pool if f.severity in BLOCKING_SEVERITIES]


def apply_review_verdict(task: Task, report: ReviewReport) -> Task:
    """Map review verdict to task status transitions."""
    verdict = report.verdict
    if verdict is ReviewVerdict.PASS:
        return apply_status_transition(task, TaskStatus.REVIEW_PASSED)
    if verdict is ReviewVerdict.PASS_WITH_NOTES:
        if unresolved_blocking_findings(report):
            raise ValidationError(
                "pass_with_notes not allowed while unresolved blocker/major findings exist"
            )
        return apply_status_transition(task, TaskStatus.REVIEW_PASSED)
    if verdict is ReviewVerdict.CHANGES_REQUIRED:
        # Return to implementation (or validating) for repair.
        if task.status is TaskStatus.READY_FOR_REVIEW:
            return apply_status_transition(task, TaskStatus.REVIEW_FAILED)
        raise ValidationError(
            f"changes_required requires ready_for_review (got {task.status.value})"
        )
    if verdict is ReviewVerdict.BLOCKED:
        updated = apply_status_transition(task, TaskStatus.BLOCKED)
        updated.blocked_reason = updated.blocked_reason or (
            report.notes or "Review verdict: blocked"
        )
        return updated
    raise ValidationError(f"Unknown review verdict: {verdict}")


def assert_implementation_report_untouched(
    recorded_fingerprint: str | None,
    current_fingerprint: str | None,
) -> None:
    """Reviewer must not silently edit the implementation report."""
    if recorded_fingerprint and current_fingerprint and recorded_fingerprint != current_fingerprint:
        raise ValidationError(
            "Implementation report fingerprint changed during review; "
            "silent edits are not allowed"
        )
