"""Allowlisted version/help/auth probes — never live prompts (Round 4D1)."""

from __future__ import annotations

import re
import subprocess
import time
from typing import Sequence

from .provider_discovery import VERSION_LINE_RE, clamp_discovery_timeout
from .provider_readiness_constants import (
    PROBE_OUTPUT_LIMIT,
    PROBE_TIMEOUT_DEFAULT,
)
from .provider_readiness_discovery import strip_ansi
from .provider_readiness_models import (
    AuthenticationStatus,
    CompatibilityStatus,
    ProbeKind,
    ProbeRecord,
    ReadinessFailureClass,
)
from .provider_readiness_profiles import ProviderReadinessProfile
from .safe_policy import PolicyError, assert_no_shell_metacharacters, assert_not_equitify_blob, filter_environment

# Global allowlist of argv tokens that may appear in readiness probes.
SAFE_PROBE_TOKENS = frozenset(
    {
        "--version",
        "version",
        "-V",
        "--help",
        "help",
        "-h",
        "auth",
        "status",
        "whoami",
        # Only valid inside exact allowlisted sequences below.
        "login",
        "exec",
    }
)

# Exact argv sequences permitted even when tokens appear in FORBIDDEN_PROBE_TOKENS.
# Bare login / exec with prompts remain forbidden via sequence + forbidden checks.
ALLOWLISTED_PROBE_ARGV_SEQUENCES: frozenset[tuple[str, ...]] = frozenset(
    {
        ("--version",),
        ("version",),
        ("-V",),
        ("--help",),
        ("help",),
        ("-h",),
        ("auth", "status"),
        ("whoami",),
        ("login", "status"),
        ("exec", "--help"),
        ("exec", "help"),
        ("exec", "-h"),
    }
)

# Tokens that indicate a prompt / live agent invocation — refuse unless full argv
# is an exact ALLOWLISTED_PROBE_ARGV_SEQUENCES entry.
FORBIDDEN_PROBE_TOKENS = frozenset(
    {
        "prompt",
        "--prompt",
        "-p",
        "chat",
        "ask",
        "agent",
        "exec",
        "run",
        "login",
        "logout",
        "refresh",
        "--yes",
        "-y",
        "--force",
        "complete",
        "completion",
    }
)

_TOKEN_RE = re.compile(r"(?i)(token|api[_-]?key|authorization|bearer)\s*[:=]\s*\S+")
_AUTH_TRUE_RE = re.compile(
    r"(?i)\b(logged[\s-]?in|authenticated|signed[\s-]?in)\b"
)
_AUTH_FALSE_RE = re.compile(
    r"(?i)\b(not\s+logged[\s-]?in|unauthenticated|logged[\s-]?out|not\s+signed[\s-]?in)\b"
)
_AUTH_CHATGPT_RE = re.compile(
    r"(?i)\b(chatgpt|chat\s*gpt|plus|pro|business|edu|enterprise|subscription)\b"
)
_AUTH_API_KEY_RE = re.compile(r"(?i)\b(api[\s_-]?key|openai[_-]?api[_-]?key)\b")


def redact_probe_text(text: str, limit: int = 400) -> str:
    cleaned = strip_ansi(text or "")
    cleaned = _TOKEN_RE.sub(r"\1=[REDACTED]", cleaned)
    cleaned = cleaned.replace("\r", " ").replace("\n", " | ")
    if len(cleaned) > limit:
        return cleaned[:limit] + "...[truncated]"
    return cleaned


def help_text_for_analysis(probe: ProbeRecord, *, limit: int = 4000) -> str:
    """Return a longer redacted help extract for advertisement/contract scans."""
    # ProbeRecord only stores the short summary; callers that need analysis should
    # pass through overrides or re-use sanitized_output_summary with a higher cap
    # when available via metadata.
    return redact_probe_text(probe.sanitized_output_summary or "", limit=limit)


def assert_probe_argv_safe(argv_tail: Sequence[str]) -> None:
    argv = tuple(str(t) for t in argv_tail)
    argv_l = tuple(t.lower() for t in argv)
    if argv in ALLOWLISTED_PROBE_ARGV_SEQUENCES or argv_l in {
        tuple(x.lower() for x in seq) for seq in ALLOWLISTED_PROBE_ARGV_SEQUENCES
    }:
        return
    for token in argv:
        low = token.lower()
        if low in FORBIDDEN_PROBE_TOKENS or token in FORBIDDEN_PROBE_TOKENS:
            raise PolicyError(f"Probe argv token refused (forbidden): {token!r}")
        if token not in SAFE_PROBE_TOKENS and low not in SAFE_PROBE_TOKENS:
            raise PolicyError(f"Probe argv token refused (not allowlisted): {token!r}")


def run_safe_probe(
    executable: str,
    argv_tail: Sequence[str],
    *,
    kind: ProbeKind,
    adapter_version: str,
    executable_fingerprint: str | None,
    timeout: float | None = None,
    output_limit: int = PROBE_OUTPUT_LIMIT,
) -> ProbeRecord:
    assert_not_equitify_blob(executable, *argv_tail)
    assert_no_shell_metacharacters([executable, *argv_tail])
    assert_probe_argv_safe(argv_tail)
    timeout_s = clamp_discovery_timeout(timeout if timeout is not None else PROBE_TIMEOUT_DEFAULT)
    argv = [executable, *argv_tail]
    command_identity = " ".join([ProbeKind(kind).value, *argv_tail])
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
            check=False,
            env=filter_environment(None),
        )
        stdout = redact_probe_text(completed.stdout or "", limit=output_limit)
        stderr = redact_probe_text(completed.stderr or "", limit=min(400, output_limit))
        combined = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        version = None
        parse_status = CompatibilityStatus.UNAVAILABLE.value
        if kind is ProbeKind.VERSION:
            for line in strip_ansi(combined).splitlines():
                match = VERSION_LINE_RE.search(line.strip())
                if match:
                    version = line.strip()[:200]
                    parse_status = CompatibilityStatus.SUPPORTED.value
                    break
            if version is None:
                parse_status = CompatibilityStatus.MALFORMED.value
        # Help summaries need more room for auth/noninteractive advertisement scans.
        summary_limit = min(output_limit, 4000) if kind is ProbeKind.HELP else 400
        summary = redact_probe_text(
            (completed.stdout or "") or (completed.stderr or ""),
            limit=summary_limit,
        )
        if stderr and not (completed.stdout or "").strip():
            summary = stderr
        return ProbeRecord(
            kind=kind.value,
            command_identity=command_identity,
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
            timeout_seconds=timeout_s,
            output_limit_bytes=output_limit,
            exit_code=int(completed.returncode),
            sanitized_output_summary=summary,
            parsed_cli_version=version,
            parse_status=parse_status,
            failure_class=ReadinessFailureClass.NONE.value
            if completed.returncode == 0
            else ReadinessFailureClass.PROBE_FAILED.value,
            duration_seconds=round(time.perf_counter() - started, 6),
        )
    except subprocess.TimeoutExpired:
        return ProbeRecord(
            kind=kind.value,
            command_identity=command_identity,
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
            timeout_seconds=timeout_s,
            output_limit_bytes=output_limit,
            exit_code=None,
            sanitized_output_summary=f"probe timed out after {timeout_s}s",
            parsed_cli_version=None,
            parse_status=CompatibilityStatus.UNAVAILABLE.value,
            failure_class=ReadinessFailureClass.TIMEOUT.value,
            duration_seconds=round(time.perf_counter() - started, 6),
        )
    except OSError as exc:
        return ProbeRecord(
            kind=kind.value,
            command_identity=command_identity,
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
            timeout_seconds=timeout_s,
            output_limit_bytes=output_limit,
            exit_code=None,
            sanitized_output_summary=f"probe spawn failed: {exc}",
            parsed_cli_version=None,
            parse_status=CompatibilityStatus.UNAVAILABLE.value,
            failure_class=ReadinessFailureClass.PROBE_FAILED.value,
            duration_seconds=round(time.perf_counter() - started, 6),
        )


def skipped_probe(
    kind: ProbeKind,
    *,
    reason: str,
    adapter_version: str,
    executable_fingerprint: str | None = None,
) -> ProbeRecord:
    return ProbeRecord(
        kind=kind.value,
        command_identity=f"{kind.value}:skipped",
        adapter_version=adapter_version,
        executable_fingerprint=executable_fingerprint,
        timeout_seconds=0.0,
        output_limit_bytes=0,
        exit_code=None,
        sanitized_output_summary=reason,
        parsed_cli_version=None,
        parse_status=CompatibilityStatus.UNAVAILABLE.value,
        failure_class=ReadinessFailureClass.NONE.value,
        skipped=True,
        skip_reason=reason,
    )


def interpret_authentication_mode(text: str) -> str:
    """Classify auth mode from safe status text only (never credential files)."""
    if _AUTH_API_KEY_RE.search(text or "") and not _AUTH_CHATGPT_RE.search(text or ""):
        return "api_key"
    if _AUTH_CHATGPT_RE.search(text or ""):
        return "chatgpt"
    if _AUTH_API_KEY_RE.search(text or ""):
        # Both mentioned — prefer explicit API-key wording as unsupported mode.
        return "api_key"
    if _AUTH_TRUE_RE.search(text or ""):
        return "unknown"
    return "none"


def interpret_auth_probe(
    probe: ProbeRecord,
) -> tuple[AuthenticationStatus, str, str]:
    """Return (authentication_status, verification_method, authentication_mode)."""
    if probe.skipped:
        return AuthenticationStatus.VERIFICATION_UNSUPPORTED, "skipped", "none"
    if probe.failure_class == ReadinessFailureClass.TIMEOUT.value:
        return AuthenticationStatus.VERIFICATION_FAILED, "timeout", "none"
    if probe.failure_class == ReadinessFailureClass.PROBE_FAILED.value and probe.exit_code not in (0, None):
        # Nonzero may still contain status text; parse carefully.
        pass
    text = probe.sanitized_output_summary or ""
    mode = interpret_authentication_mode(text)
    if _AUTH_FALSE_RE.search(text):
        return AuthenticationStatus.UNAUTHENTICATED_VERIFIED, "auth_status_command", "none"
    if _AUTH_TRUE_RE.search(text):
        if mode == "none":
            mode = "unknown"
        return AuthenticationStatus.AUTHENTICATED_VERIFIED, "auth_status_command", mode
    if probe.exit_code == 0 and text.strip():
        return AuthenticationStatus.UNKNOWN, "auth_status_inconclusive", mode if mode != "none" else "unknown"
    if probe.exit_code not in (0, None):
        return AuthenticationStatus.VERIFICATION_FAILED, "auth_status_nonzero", "none"
    return AuthenticationStatus.UNKNOWN, "auth_status_inconclusive", "none"


def probe_provider(
    executable: str,
    profile: ProviderReadinessProfile,
    *,
    adapter_version: str,
    executable_fingerprint: str | None,
    include_help: bool = False,
    timeout: float | None = None,
    auth_argv_override: Sequence[str] | None = None,
    force_help_for_auth_plan: bool = False,
) -> dict[str, ProbeRecord]:
    """Run allowlisted probes for one provider executable."""
    results: dict[str, ProbeRecord] = {}

    version_argv = profile.version_argv
    if version_argv:
        results["version"] = run_safe_probe(
            executable,
            version_argv,
            kind=ProbeKind.VERSION,
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
            timeout=timeout,
        )
    else:
        results["version"] = skipped_probe(
            ProbeKind.VERSION,
            reason="no version probe configured for provider",
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
        )

    need_help = include_help or force_help_for_auth_plan or (
        getattr(profile, "auth_probe_mode", "profile_only") == "help_confirmed_allowlist"
        and not profile.auth_argv
        and auth_argv_override is None
    )
    if need_help and profile.help_argv:
        results["help"] = run_safe_probe(
            executable,
            profile.help_argv,
            kind=ProbeKind.HELP,
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
            timeout=timeout,
        )
    else:
        results["help"] = skipped_probe(
            ProbeKind.HELP,
            reason="help probe not requested or not configured",
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
        )

    auth_argv = tuple(auth_argv_override) if auth_argv_override is not None else None
    if auth_argv is None and profile.auth_argv:
        auth_argv = tuple(profile.auth_argv)

    if auth_argv:
        results["auth"] = run_safe_probe(
            executable,
            auth_argv,
            kind=ProbeKind.AUTH_STATUS,
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
            timeout=timeout,
        )
    else:
        results["auth"] = skipped_probe(
            ProbeKind.AUTH_STATUS,
            reason=(
                "authentication status probe unsupported for provider; "
                "not inferred from credential files"
            ),
            adapter_version=adapter_version,
            executable_fingerprint=executable_fingerprint,
        )

    return results
