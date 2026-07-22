"""Host/system final verdict mapping for Round 4D1.2."""

from __future__ import annotations

from enum import Enum
from typing import Any, Sequence

from .provider_readiness_models import (
    AuthenticationStatus,
    NoninteractiveStatus,
    ReadinessVerdict,
    RoleEligibility,
)


class HostSystemVerdict(str, Enum):
    LIVE_SMOKE_READY = "live_smoke_ready"
    LIVE_SMOKE_READY_WITH_OPERATOR_AUTH = "live_smoke_ready_with_operator_auth"
    AUTHENTICATION_UNVERIFIED = "authentication_unverified"
    NONINTERACTIVE_UNVERIFIED = "noninteractive_unverified"
    NO_INDEPENDENT_REVIEWER = "no_independent_reviewer"
    PROVIDER_NOT_ELIGIBLE = "provider_not_eligible"


_AUTH_BLOCKING = frozenset(
    {
        AuthenticationStatus.UNKNOWN.value,
        AuthenticationStatus.VERIFICATION_UNSUPPORTED.value,
        AuthenticationStatus.VERIFICATION_FAILED.value,
        AuthenticationStatus.REPORTED_AUTHENTICATED.value,
        AuthenticationStatus.UNAUTHENTICATED_VERIFIED.value,
    }
)

_NI_BLOCKING = frozenset(
    {
        NoninteractiveStatus.UNAVAILABLE.value,
        NoninteractiveStatus.UNSUPPORTED_VERIFIED.value,
        NoninteractiveStatus.AMBIGUOUS.value,
    }
)

_POSITIVE = frozenset(
    {
        ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
        ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
    }
)


def compute_host_system_verdict(
    records: Sequence[Any],
    *,
    independence_status: str | None = None,
    combinations: Sequence[Any] | None = None,
) -> str:
    """Pick exactly one host/system verdict (priority order from Round 4D1.2 design)."""
    recs = [r for r in records if getattr(r, "provider_id", None) != "simulated"]
    if not recs and records:
        recs = list(records)

    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # 1) live_smoke_ready
    if any(
        _get(r, "final_readiness_verdict")
        == ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value
        for r in recs
    ):
        return HostSystemVerdict.LIVE_SMOKE_READY.value

    # 2) live_smoke_ready_with_operator_auth
    if any(
        _get(r, "final_readiness_verdict")
        == ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value
        for r in recs
    ):
        return HostSystemVerdict.LIVE_SMOKE_READY_WITH_OPERATOR_AUTH.value

    installed = [
        r
        for r in recs
        if _get(r, "discovery_status") == "installed"
        or _get(r, "final_readiness_verdict")
        in (
            ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value,
            ReadinessVerdict.INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED.value,
            ReadinessVerdict.INSTALLED_BUT_VERSION_UNSUPPORTED.value,
        )
        or _get(r, "final_readiness_verdict") in _POSITIVE
    ]

    # Prefer auth gate when any installed provider is blocked primarily on auth.
    auth_blocked = [
        r
        for r in installed
        if _get(r, "authentication_status") in _AUTH_BLOCKING
        and _get(r, "final_readiness_verdict")
        == ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    ]
    if auth_blocked:
        return HostSystemVerdict.AUTHENTICATION_UNVERIFIED.value

    # Noninteractive gate (auth cleared or not the recorded primary blocker).
    ni_blocked = [
        r
        for r in installed
        if _get(r, "noninteractive_status") in _NI_BLOCKING
        or _get(r, "final_readiness_verdict")
        == ReadinessVerdict.INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED.value
    ]
    if ni_blocked:
        return HostSystemVerdict.NONINTERACTIVE_UNVERIFIED.value

    # Implementer exists but no independent reviewer.
    impl_ok = any(
        _get(r, "implementer_eligibility")
        in (
            RoleEligibility.ELIGIBLE.value,
            RoleEligibility.CONDITIONALLY_ELIGIBLE.value,
        )
        for r in recs
    )
    indep = independence_status or ""
    combo_cats = set()
    for c in combinations or []:
        combo_cats.add(_get(c, "category", ""))
    if impl_ok and (
        indep in ("unavailable", "fresh_context_same_provider_only", "independence_unverified")
        or "no_safe_independent_reviewer" in combo_cats
        or "deterministic_review_only" in combo_cats
        or "fresh_context_same_provider" in combo_cats
    ):
        # Only if somehow past auth/ni — still flag independence gap.
        if not any(
            _get(c, "category") == "separate_provider" for c in (combinations or [])
        ):
            return HostSystemVerdict.NO_INDEPENDENT_REVIEWER.value

    return HostSystemVerdict.PROVIDER_NOT_ELIGIBLE.value
