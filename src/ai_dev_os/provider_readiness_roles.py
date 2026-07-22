"""Role eligibility and reviewer independence matrix (Round 4D1)."""

from __future__ import annotations

from .provider_readiness_models import (
    AuthenticationStatus,
    NoninteractiveStatus,
    ProviderCombination,
    READINESS_ROLES,
    ReviewerIndependence,
    RoleEligibility,
    RoleMatrixEntry,
)
from .provider_readiness_profiles import ProviderReadinessProfile


def _auth_ready(status: str) -> bool:
    return status == AuthenticationStatus.AUTHENTICATED_VERIFIED.value


def _ni_ready(status: str) -> bool:
    return status in (
        NoninteractiveStatus.SUPPORTED_VERIFIED.value,
        NoninteractiveStatus.SUPPORTED_DOCUMENTED.value,
    )


def build_role_matrix(
    profile: ProviderReadinessProfile,
    *,
    authentication_status: str,
    noninteractive_status: str,
    provider_mode: str,
    discovery_installed: bool,
) -> list[RoleMatrixEntry]:
    entries: list[RoleMatrixEntry] = []
    policy_blocked = provider_mode == "live_local_cli_allowed"
    for role in READINESS_ROLES:
        adapter_supported = role in profile.adapter_roles
        technically = adapter_supported and discovery_installed and not profile.synthetic
        if profile.synthetic:
            technically = False  # not a live technical candidate
        auth_ok = _auth_ready(authentication_status)
        ni_ok = _ni_ready(noninteractive_status)
        if policy_blocked:
            eligibility = RoleEligibility.POLICY_BLOCKED.value
        elif not adapter_supported:
            eligibility = RoleEligibility.INELIGIBLE.value
        elif not discovery_installed:
            eligibility = RoleEligibility.INELIGIBLE.value
        elif profile.synthetic:
            eligibility = RoleEligibility.INELIGIBLE.value
        elif auth_ok and ni_ok:
            eligibility = RoleEligibility.ELIGIBLE.value
        elif ni_ok and authentication_status in (
            AuthenticationStatus.UNKNOWN.value,
            AuthenticationStatus.VERIFICATION_UNSUPPORTED.value,
        ):
            eligibility = RoleEligibility.CONDITIONALLY_ELIGIBLE.value
        elif discovery_installed and adapter_supported:
            eligibility = RoleEligibility.UNVERIFIED.value
        else:
            eligibility = RoleEligibility.INELIGIBLE.value
        entries.append(
            RoleMatrixEntry(
                role=role,
                technically_supported=technically,
                adapter_supported=adapter_supported,
                policy_allowed=not policy_blocked and adapter_supported,
                authentication_ready=auth_ok,
                noninteractive_ready=ni_ok,
                eligibility=eligibility,
            )
        )
    return entries


def role_eligibility(matrix: list[RoleMatrixEntry], role: str) -> str:
    for entry in matrix:
        if entry.role == role:
            return entry.eligibility
    return RoleEligibility.INELIGIBLE.value


def compute_independence(
    records: list[dict],
) -> tuple[str, list[ProviderCombination]]:
    """Build combinations from provider readiness dict summaries.

    Each record dict needs: provider_id, implementer_eligibility, reviewer_eligibility,
    final_readiness_verdict.
    """
    implementers = [
        r
        for r in records
        if r.get("implementer_eligibility")
        in (
            RoleEligibility.ELIGIBLE.value,
            RoleEligibility.CONDITIONALLY_ELIGIBLE.value,
        )
        and r.get("provider_id") != "simulated"
    ]
    reviewers = [
        r
        for r in records
        if r.get("reviewer_eligibility")
        in (
            RoleEligibility.ELIGIBLE.value,
            RoleEligibility.CONDITIONALLY_ELIGIBLE.value,
        )
        and r.get("provider_id") != "simulated"
    ]

    combinations: list[ProviderCombination] = []
    independence = ReviewerIndependence.UNAVAILABLE.value

    for impl in implementers:
        for rev in reviewers:
            if impl["provider_id"] == rev["provider_id"]:
                continue
            combinations.append(
                ProviderCombination(
                    category="separate_provider",
                    implementer_provider_id=impl["provider_id"],
                    reviewer_provider_id=rev["provider_id"],
                    independence_status=ReviewerIndependence.SEPARATE_PROVIDER_AVAILABLE.value,
                    notes="Different providers for implementer and reviewer",
                    recommended=False,
                )
            )

    if combinations:
        independence = ReviewerIndependence.SEPARATE_PROVIDER_AVAILABLE.value
        combinations[0].recommended = True
    elif implementers and reviewers:
        # Same provider both roles
        impl = implementers[0]
        combinations.append(
            ProviderCombination(
                category="fresh_context_same_provider",
                implementer_provider_id=impl["provider_id"],
                reviewer_provider_id=impl["provider_id"],
                independence_status=ReviewerIndependence.FRESH_CONTEXT_SAME_PROVIDER_ONLY.value,
                notes=(
                    "Only one provider eligible; reviewer independence limited to "
                    "fresh context — not true independence"
                ),
                recommended=True,
            )
        )
        independence = ReviewerIndependence.FRESH_CONTEXT_SAME_PROVIDER_ONLY.value
    elif implementers:
        impl = implementers[0]
        combinations.append(
            ProviderCombination(
                category="deterministic_review_only",
                implementer_provider_id=impl["provider_id"],
                reviewer_provider_id=None,
                independence_status=ReviewerIndependence.UNAVAILABLE.value,
                notes="Implementer eligible; no independent provider reviewer available",
                recommended=True,
            )
        )
        independence = ReviewerIndependence.UNAVAILABLE.value
    else:
        combinations.append(
            ProviderCombination(
                category="no_safe_independent_reviewer",
                implementer_provider_id=None,
                reviewer_provider_id=None,
                independence_status=ReviewerIndependence.UNAVAILABLE.value,
                notes="No eligible implementer/reviewer combination",
                recommended=False,
            )
        )

    # Prefer recommending separate provider if multiple.
    for combo in combinations:
        if combo.category == "separate_provider":
            for c in combinations:
                c.recommended = False
            combo.recommended = True
            break

    return independence, combinations
