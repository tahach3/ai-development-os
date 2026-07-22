"""Deterministic provider readiness eligibility policy (Round 4D1)."""

from __future__ import annotations

from .provider_readiness_models import (
    AuthenticationStatus,
    CapabilityStatus,
    CompatibilityStatus,
    DiscoveryStatus,
    NoninteractiveStatus,
    ReadinessVerdict,
    RoleEligibility,
)


def decide_provider_verdict(
    *,
    discovery_status: str,
    compatibility_status: str,
    authentication_status: str,
    noninteractive_status: str,
    implementer_eligibility: str,
    reviewer_eligibility: str,
    live_policy_status: str,
    provider_mode: str,
    provider_id: str,
    allow_unknown_auth_conditional: bool = False,
) -> tuple[str, list[str], list[str]]:
    """Return (verdict, blockers, warnings). Never enables live mode."""
    blockers: list[str] = []
    warnings: list[str] = []

    if provider_id == "simulated":
        blockers.append("simulated_provider_not_eligible_for_live_smoke")
        return ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value, blockers, warnings

    if discovery_status == DiscoveryStatus.AMBIGUOUS_INSTALLATION.value:
        blockers.append("ambiguous_executable_installation")
        return ReadinessVerdict.AMBIGUOUS_PROVIDER_INSTALLATION.value, blockers, warnings

    if discovery_status == DiscoveryStatus.EXECUTABLE_UNTRUSTED.value:
        blockers.append("executable_failed_trust_checks")
        return ReadinessVerdict.POLICY_BLOCKED.value, blockers, warnings

    if discovery_status == DiscoveryStatus.PROBE_FAILED.value:
        blockers.append("discovery_probe_failed")
        return ReadinessVerdict.PROBE_FAILED.value, blockers, warnings

    if discovery_status == DiscoveryStatus.NOT_INSTALLED.value:
        blockers.append("provider_not_installed")
        return ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value, blockers, warnings

    if compatibility_status == CompatibilityStatus.UNSUPPORTED.value:
        blockers.append("cli_version_unsupported")
        return ReadinessVerdict.INSTALLED_BUT_VERSION_UNSUPPORTED.value, blockers, warnings

    if compatibility_status == CompatibilityStatus.MALFORMED.value:
        blockers.append("cli_version_malformed")
        return ReadinessVerdict.PROBE_FAILED.value, blockers, warnings

    if provider_mode == "disabled":
        warnings.append("provider_mode_disabled_in_config_must_be_enabled_before_4d2")

    if live_policy_status not in (
        "disabled_for_round_4d1",
        "live_gated_but_disabled",
        "disabled",
    ):
        # Defensive: unexpected live-on during 4D1 is a security block.
        blockers.append("unexpected_live_policy_state")
        return ReadinessVerdict.POLICY_BLOCKED.value, blockers, warnings

    # Live must remain off during readiness; if config claims live allowed, block.
    if provider_mode == "live_local_cli_allowed":
        blockers.append("live_mode_configured_but_round_4d1_forbids_enabling_or_using_live")
        warnings.append("do_not_use_live_from_readiness_tooling")
        return ReadinessVerdict.POLICY_BLOCKED.value, blockers, warnings

    auth = authentication_status
    if auth in (
        AuthenticationStatus.UNKNOWN.value,
        AuthenticationStatus.VERIFICATION_UNSUPPORTED.value,
        AuthenticationStatus.VERIFICATION_FAILED.value,
        AuthenticationStatus.REPORTED_AUTHENTICATED.value,
    ):
        if not allow_unknown_auth_conditional:
            blockers.append("authentication_not_verified")
            return (
                ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value,
                blockers,
                warnings,
            )
        warnings.append("authentication_unknown_requires_operator_approval_before_4d2")

    if auth == AuthenticationStatus.UNAUTHENTICATED_VERIFIED.value:
        blockers.append("provider_unauthenticated")
        return (
            ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value,
            blockers,
            warnings,
        )

    ni = noninteractive_status
    if ni in (
        NoninteractiveStatus.UNAVAILABLE.value,
        NoninteractiveStatus.UNSUPPORTED_VERIFIED.value,
        NoninteractiveStatus.AMBIGUOUS.value,
    ):
        blockers.append("noninteractive_not_ready")
        return (
            ReadinessVerdict.INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED.value,
            blockers,
            warnings,
        )

    if ni == NoninteractiveStatus.SUPPORTED_DOCUMENTED.value:
        warnings.append("noninteractive_documented_not_live_verified")

    role_ok = implementer_eligibility in (
        RoleEligibility.ELIGIBLE.value,
        RoleEligibility.CONDITIONALLY_ELIGIBLE.value,
    ) or reviewer_eligibility in (
        RoleEligibility.ELIGIBLE.value,
        RoleEligibility.CONDITIONALLY_ELIGIBLE.value,
    )
    if not role_ok:
        blockers.append("no_eligible_roles")
        return ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value, blockers, warnings

    if (
        auth == AuthenticationStatus.AUTHENTICATED_VERIFIED.value
        and ni == NoninteractiveStatus.SUPPORTED_VERIFIED.value
        and compatibility_status == CompatibilityStatus.SUPPORTED.value
        and implementer_eligibility == RoleEligibility.ELIGIBLE.value
    ):
        return ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value, blockers, warnings

    # Documented noninteractive + verified auth → conditional if roles ok.
    if (
        auth == AuthenticationStatus.AUTHENTICATED_VERIFIED.value
        and ni == NoninteractiveStatus.SUPPORTED_DOCUMENTED.value
    ):
        warnings.append("bounded_live_smoke_requires_explicit_4d2_authorization")
        return (
            ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
            blockers,
            warnings,
        )

    if allow_unknown_auth_conditional and ni in (
        NoninteractiveStatus.SUPPORTED_VERIFIED.value,
        NoninteractiveStatus.SUPPORTED_DOCUMENTED.value,
    ):
        return (
            ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
            blockers,
            warnings,
        )

    blockers.append("readiness_conditions_unmet")
    return ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value, blockers, warnings


def aggregate_verdict(provider_verdicts: list[str]) -> str:
    order = [
        ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
        ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value,
        ReadinessVerdict.INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED.value,
        ReadinessVerdict.INSTALLED_BUT_VERSION_UNSUPPORTED.value,
        ReadinessVerdict.AMBIGUOUS_PROVIDER_INSTALLATION.value,
        ReadinessVerdict.POLICY_BLOCKED.value,
        ReadinessVerdict.PROBE_FAILED.value,
        ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value,
        ReadinessVerdict.INVALID_RECORD.value,
    ]
    present = set(provider_verdicts)
    for v in order:
        if v in present:
            # Prefer strongest positive if any eligible/conditional exists.
            if v in (
                ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
                ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
            ):
                return v
    for v in order:
        if v in present and v != ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value:
            return v
    return ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value


def capability_from_adapter_contract(*, documented: bool, verified: bool = False) -> str:
    if verified:
        return CapabilityStatus.SUPPORTED_VERIFIED.value
    if documented:
        return CapabilityStatus.SUPPORTED_DOCUMENTED.value
    return CapabilityStatus.UNAVAILABLE.value
