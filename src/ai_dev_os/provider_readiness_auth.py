"""Authentication-status advertisement and allowlisted probe resolution (Round 4D1.2)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Sequence

from .provider_readiness_probes import SAFE_PROBE_TOKENS, assert_probe_argv_safe
from .safe_policy import PolicyError

# Exact allowlisted auth-status argv sequences (never login/refresh).
ALLOWLISTED_AUTH_ARGV: tuple[tuple[str, ...], ...] = (
    ("auth", "status"),
    ("whoami",),
)

_AUTH_AD_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"(?i)\bauth\s+status\b"), ("auth", "status")),
    (re.compile(r"(?i)\bwhoami\b"), ("whoami",)),
)

# Help phrases that suggest interactive login — never treat as status probe.
_LOGIN_HINT_RE = re.compile(r"(?i)\b(login|logout|sign[\s-]?in|refresh[\s-]?token|oauth)\b")


@dataclass(frozen=True)
class AuthProbePlan:
    """Decision about whether a safe auth-status probe may run."""

    advertised: bool
    runnable: bool
    argv: tuple[str, ...] | None
    reason: str
    source: str  # profile | help_confirmed_allowlist | none

    def to_dict(self) -> dict:
        return asdict(self)


def scan_help_for_auth_status(help_text: str | None) -> tuple[bool, tuple[str, ...] | None, str]:
    """Parse help as untrusted data for allowlisted auth-status advertisements.

    Returns (advertised, argv_or_none, note). Never executes anything.
    """
    text = help_text or ""
    if not text.strip():
        return False, None, "help_empty"
    # Prefer auth status over whoami when both appear.
    for pattern, argv in _AUTH_AD_PATTERNS:
        if pattern.search(text):
            # If only login hints without status context for whoami-only, still OK —
            # but refuse if the ONLY auth-related hit is login/logout without status.
            try:
                assert_probe_argv_safe(argv)
            except PolicyError:
                return False, None, "advertised_argv_not_allowlisted"
            return True, argv, f"help_advertises:{' '.join(argv)}"
    if _LOGIN_HINT_RE.search(text):
        return False, None, "help_mentions_login_without_status_command"
    return False, None, "help_no_auth_status_command"


def resolve_auth_probe_plan(
    *,
    profile_auth_argv: Sequence[str] | None,
    auth_probe_mode: str,
    help_text: str | None,
) -> AuthProbePlan:
    """Decide auth probe argv under Round 4D1.2 policy.

    Modes:
    - ``profile_only`` — only profile.auth_argv
    - ``help_confirmed_allowlist`` — profile OR help-confirmed allowlisted pattern
    - ``never`` — never probe
    """
    if auth_probe_mode == "never":
        return AuthProbePlan(
            advertised=False,
            runnable=False,
            argv=None,
            reason="auth_probe_mode_never",
            source="none",
        )

    if profile_auth_argv:
        argv = tuple(profile_auth_argv)
        try:
            assert_probe_argv_safe(argv)
        except PolicyError as exc:
            return AuthProbePlan(
                advertised=False,
                runnable=False,
                argv=None,
                reason=f"profile_auth_argv_refused:{exc}",
                source="none",
            )
        if argv not in ALLOWLISTED_AUTH_ARGV and not all(
            t in SAFE_PROBE_TOKENS or t.lower() in SAFE_PROBE_TOKENS for t in argv
        ):
            return AuthProbePlan(
                advertised=False,
                runnable=False,
                argv=None,
                reason="profile_auth_argv_not_in_known_safe_set",
                source="none",
            )
        return AuthProbePlan(
            advertised=True,
            runnable=True,
            argv=argv,
            reason="profile_declared_auth_argv",
            source="profile",
        )

    advertised, help_argv, note = scan_help_for_auth_status(help_text)
    if auth_probe_mode == "help_confirmed_allowlist" and advertised and help_argv:
        return AuthProbePlan(
            advertised=True,
            runnable=True,
            argv=help_argv,
            reason=note,
            source="help_confirmed_allowlist",
        )

    if advertised and help_argv:
        return AuthProbePlan(
            advertised=True,
            runnable=False,
            argv=help_argv,
            reason=f"advertised_but_mode_forbids_probe:{auth_probe_mode};{note}",
            source="none",
        )

    return AuthProbePlan(
        advertised=False,
        runnable=False,
        argv=None,
        reason=note if help_text is not None else "no_safe_auth_status_command",
        source="none",
    )
