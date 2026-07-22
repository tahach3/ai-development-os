"""Provider-specific readiness profiles (Round 4D1)."""

from __future__ import annotations

from dataclasses import dataclass

from .provider_models import PROVIDER_ADAPTER_VERSION


@dataclass(frozen=True)
class ProviderReadinessProfile:
    provider_id: str
    display_name: str
    version_argv: tuple[str, ...]
    help_argv: tuple[str, ...]
    auth_argv: tuple[str, ...] | None
    adapter_roles: tuple[str, ...]
    # Noninteractive assessment from adapter contracts (not live proof).
    noninteractive_documented: bool
    # Cursor desktop must not be treated as automation CLI.
    requires_automation_cli_proof: bool = False
    min_version: tuple[int, ...] | None = None
    max_version: tuple[int, ...] | None = None
    network_behavior: str = "may_contact_provider_backend"
    notes: str = ""
    # Synthetic-only: treat noninteractive as verified via test contract.
    synthetic_verified_noninteractive: bool = False
    # For tests: force auth interpretation without real auth command.
    synthetic: bool = False


PROFILES: dict[str, ProviderReadinessProfile] = {
    "claude_code": ProviderReadinessProfile(
        provider_id="claude_code",
        display_name="Claude Code CLI",
        version_argv=("--version",),
        help_argv=("--help",),
        # Uncertain whether auth status is safely non-interactive → do not probe.
        auth_argv=None,
        adapter_roles=("implementer", "repair_implementer", "planner"),
        noninteractive_documented=True,
        requires_automation_cli_proof=False,
        notes=(
            "Distinguish interactive chat from noninteractive execution; "
            "do not assume subscription vs API-key auth; auth probe unsupported."
        ),
    ),
    "codex": ProviderReadinessProfile(
        provider_id="codex",
        display_name="OpenAI Codex CLI",
        version_argv=("--version",),
        help_argv=("--help",),
        auth_argv=None,
        adapter_roles=("reviewer", "final_verifier", "planner"),
        noninteractive_documented=True,
        notes=(
            "Distinguish interactive vs noninteractive; auth verification unsupported "
            "without dedicated safe status command."
        ),
    ),
    "cursor": ProviderReadinessProfile(
        provider_id="cursor",
        display_name="Cursor CLI",
        version_argv=("--version",),
        help_argv=("--help",),
        auth_argv=None,
        adapter_roles=("implementer", "repair_implementer"),
        noninteractive_documented=False,
        requires_automation_cli_proof=True,
        notes=(
            "Cursor desktop application is not an automation-capable agent CLI; "
            "editor executable alone is insufficient for noninteractive live smoke."
        ),
    ),
    "simulated": ProviderReadinessProfile(
        provider_id="simulated",
        display_name="Simulated Provider",
        version_argv=(),
        help_argv=(),
        auth_argv=None,
        adapter_roles=(
            "planner",
            "implementer",
            "reviewer",
            "repair_implementer",
            "final_verifier",
        ),
        noninteractive_documented=True,
        synthetic_verified_noninteractive=True,
        synthetic=True,
        network_behavior="none_expected",
        notes="Simulation only; not eligible for live smoke.",
    ),
}


def get_profile(provider_id: str) -> ProviderReadinessProfile:
    if provider_id not in PROFILES:
        return ProviderReadinessProfile(
            provider_id=provider_id,
            display_name=provider_id,
            version_argv=("--version",),
            help_argv=("--help",),
            auth_argv=None,
            adapter_roles=(),
            noninteractive_documented=False,
            notes="Unknown provider profile; treated as unsupported for live smoke.",
        )
    return PROFILES[provider_id]


def parse_semver_tuple(version_text: str | None) -> tuple[int, ...] | None:
    if not version_text:
        return None
    import re

    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version_text)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    return (major, minor, patch)


def version_compatible(
    version_text: str | None,
    profile: ProviderReadinessProfile,
) -> str:
    from .provider_readiness_models import CompatibilityStatus

    if not version_text:
        return CompatibilityStatus.UNAVAILABLE.value
    parsed = parse_semver_tuple(version_text)
    if parsed is None:
        return CompatibilityStatus.MALFORMED.value
    if profile.min_version and parsed < profile.min_version:
        return CompatibilityStatus.UNSUPPORTED.value
    if profile.max_version and parsed > profile.max_version:
        return CompatibilityStatus.UNSUPPORTED.value
    if profile.min_version is None and profile.max_version is None:
        # Known adapter with clean parse and no declared constraints.
        if profile.provider_id in PROFILES and not profile.synthetic:
            return CompatibilityStatus.SUPPORTED.value
        if profile.synthetic:
            return CompatibilityStatus.SUPPORTED.value
        return CompatibilityStatus.UNVERIFIED.value
    return CompatibilityStatus.SUPPORTED.value


def adapter_version_for(provider_id: str) -> str:
    return PROVIDER_ADAPTER_VERSION
