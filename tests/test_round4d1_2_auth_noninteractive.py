"""Round 4D1.2 auth + noninteractive readiness — synthetic fixtures only."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ai_dev_os.models import ProjectRecord
from ai_dev_os.project_registry import ProjectRegistry
from ai_dev_os.provider_config import ProviderConfig, ProviderEntryConfig
from ai_dev_os.provider_models import ProviderMode
from ai_dev_os.provider_readiness_auth import (
    resolve_auth_probe_plan,
    scan_help_for_auth_status,
)
from ai_dev_os.provider_readiness_engine import ProviderReadinessEngine
from ai_dev_os.provider_readiness_host_verdict import (
    HostSystemVerdict,
    compute_host_system_verdict,
)
from ai_dev_os.provider_readiness_models import (
    AuthenticationStatus,
    NoninteractiveStatus,
    ReadinessVerdict,
    RoleEligibility,
)
from ai_dev_os.provider_readiness_noninteractive import (
    assess_noninteractive_contract,
    build_synthetic_headless_argv,
)
from ai_dev_os.provider_readiness_probes import assert_probe_argv_safe, interpret_auth_probe
from ai_dev_os.provider_readiness_profiles import ProviderReadinessProfile, get_profile
from ai_dev_os.provider_readiness_store import ProviderReadinessStore
from ai_dev_os.safe_policy import PolicyError


def _write_fake_cli(
    path: Path,
    *,
    version: str = "1.2.3",
    auth: str | None = None,
    advertise_auth_in_help: bool = False,
    editor_help: bool = False,
    headless_help: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_win = os.name == "nt"
    help_bits = ["Usage: fake-cli --version --help"]
    if advertise_auth_in_help:
        help_bits.append("auth status - Show authentication status")
    if editor_help:
        help_bits.extend(
            [
                "--diff Compare two files",
                "--goto Open a file at the path",
                "--new-window Force to open a new window",
                "--list-extensions List the installed extensions",
            ]
        )
    if headless_help:
        help_bits.extend(
            [
                "--print Non-interactive print mode",
                "--output-format json Structured output",
                "--cwd Working directory binding",
                "--timeout Timeout seconds",
            ]
        )

    if is_win:
        script = path.with_suffix(".cmd") if path.suffix.lower() not in {".cmd", ".bat", ".exe"} else path
        lines = ["@echo off"]
        lines.append(f'if "%~1"=="--version" (echo fake-cli {version} & exit /b 0)')
        # One echo per help line — avoid cmd bracket/pipe parsing hazards.
        help_block = " & ".join(f"echo {bit}" for bit in help_bits)
        lines.append(f'if "%~1"=="--help" ({help_block} & exit /b 0)')
        if auth == "yes":
            lines.append('if "%~1"=="auth" if "%~2"=="status" (echo logged in as user & exit /b 0)')
        elif auth == "no":
            lines.append('if "%~1"=="auth" if "%~2"=="status" (echo not logged in & exit /b 0)')
        elif auth == "inconclusive":
            lines.append('if "%~1"=="auth" if "%~2"=="status" (echo session ok & exit /b 0)')
        lines.append("echo unknown & exit /b 2")
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return script

    script = path
    help_line = "\\n".join(help_bits)
    parts = [
        "#!/bin/sh",
        'case "$1" in',
        f'  --version|version) echo "fake-cli {version}"; exit 0 ;;',
        f'  --help|help) printf \'%s\\n\' "{help_line}"; exit 0 ;;',
    ]
    if auth == "yes":
        parts.append('  auth) if [ "$2" = "status" ]; then echo "logged in as user"; exit 0; fi ;;')
    elif auth == "no":
        parts.append('  auth) if [ "$2" = "status" ]; then echo "not logged in"; exit 0; fi ;;')
    elif auth == "inconclusive":
        parts.append('  auth) if [ "$2" = "status" ]; then echo "session ok"; exit 0; fi ;;')
    parts.extend(["  *) echo unknown; exit 2 ;;", "esac"])
    script.write_text("\n".join(parts) + "\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _config() -> ProviderConfig:
    providers = {}
    for pid in ("claude_code", "codex", "cursor", "simulated"):
        providers[pid] = ProviderEntryConfig(
            provider_id=pid,
            enabled=True,
            mode=ProviderMode.DISCOVERY_ONLY,
            allow_live=False,
        )
    return ProviderConfig(providers=providers)


@pytest.fixture
def env(tmp_path: Path):
    import tempfile

    demo = Path(tempfile.mkdtemp(prefix="aidos_calc_demo_"))
    (demo / "README.md").write_text("demo\n", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(
        ProjectRecord(id="calc-demo", name="Calc", root_path=str(demo), metadata={})
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    engine = ProviderReadinessEngine(
        repo_root=tmp_path,
        config=_config(),
        registry=registry,
    )
    return {
        "tmp": tmp_path,
        "bin": bin_dir,
        "engine": engine,
        "store": ProviderReadinessStore(tmp_path / "provider_readiness"),
    }


def test_scan_help_auth_advertisement_and_login_only():
    adv, argv, note = scan_help_for_auth_status("Commands:\n  auth status\n  login")
    assert adv is True
    assert argv == ("auth", "status")
    adv2, argv2, note2 = scan_help_for_auth_status("Use login to authenticate")
    assert adv2 is False
    assert argv2 is None
    assert "login" in note2


def test_resolve_auth_probe_plan_modes():
    never = resolve_auth_probe_plan(
        profile_auth_argv=None, auth_probe_mode="never", help_text="auth status"
    )
    assert never.runnable is False
    profile = resolve_auth_probe_plan(
        profile_auth_argv=("auth", "status"),
        auth_probe_mode="profile_only",
        help_text=None,
    )
    assert profile.runnable and profile.source == "profile"
    help_plan = resolve_auth_probe_plan(
        profile_auth_argv=None,
        auth_probe_mode="help_confirmed_allowlist",
        help_text="auth status Show authentication status",
    )
    assert help_plan.runnable and help_plan.argv == ("auth", "status")
    blocked = resolve_auth_probe_plan(
        profile_auth_argv=None,
        auth_probe_mode="profile_only",
        help_text="auth status",
    )
    assert blocked.advertised and not blocked.runnable


def test_forbidden_login_argv():
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["login"])
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["auth", "login"])


def test_auth_verified_via_help_confirmed_probe(env):
    bin_dir = env["bin"]
    _write_fake_cli(
        bin_dir / "claude",
        auth="yes",
        advertise_auth_in_help=True,
        headless_help=True,
    )
    rec = env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.auth_status_command_advertised is True
    assert rec.authentication_status == AuthenticationStatus.AUTHENTICATED_VERIFIED.value
    assert rec.live_provider_invocations == 0
    assert rec.final_readiness_verdict in (
        ReadinessVerdict.CONDITIONALLY_ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
        ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value,
        ReadinessVerdict.INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED.value,
    )


def test_auth_unauthenticated_verified(env):
    bin_dir = env["bin"]
    _write_fake_cli(bin_dir / "claude", auth="no", advertise_auth_in_help=True)
    rec = env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.authentication_status == AuthenticationStatus.UNAUTHENTICATED_VERIFIED.value
    assert rec.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    )


def test_auth_unknown_inconclusive_not_authenticated(env):
    bin_dir = env["bin"]
    _write_fake_cli(bin_dir / "claude", auth="inconclusive", advertise_auth_in_help=True)
    rec = env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.authentication_status == AuthenticationStatus.UNKNOWN.value
    assert rec.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    )


def test_no_auth_command_verification_unsupported(env):
    bin_dir = env["bin"]
    _write_fake_cli(bin_dir / "claude")
    rec = env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.authentication_status == AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
    assert rec.auth_status_command_advertised is False


def test_editor_cli_noninteractive_unsupported_verified():
    profile = get_profile("cursor")
    assessment = assess_noninteractive_contract(
        profile,
        discovery_installed=True,
        help_text=(
            "Usage: cursor.exe [options]\n"
            "-d --diff <file> <file> Compare two files\n"
            "-g --goto <file:line> Open a file at the path\n"
            "-n --new-window Force to open a new window\n"
            "--list-extensions List the installed extensions\n"
        ),
    )
    assert assessment.editor_cli_detected is True
    assert assessment.overall_status == NoninteractiveStatus.UNSUPPORTED_VERIFIED.value
    assert "prompt_input" in {d.name for d in assessment.dimensions}


def test_documented_and_synthetic_noninteractive():
    profile = get_profile("claude_code")
    documented = assess_noninteractive_contract(
        profile,
        discovery_installed=True,
        help_text="--print --output-format json --cwd /tmp --timeout 30",
    )
    assert documented.overall_status == NoninteractiveStatus.SUPPORTED_DOCUMENTED.value
    verified = assess_noninteractive_contract(
        profile,
        discovery_installed=True,
        help_text="--print",
        synthetic_verified=True,
    )
    assert verified.overall_status == NoninteractiveStatus.SUPPORTED_VERIFIED.value
    assert build_synthetic_headless_argv("claude_code") is not None
    assert build_synthetic_headless_argv("claude_code", include_prompt_text=True) is None
    assert build_synthetic_headless_argv("cursor") is None


def test_cursor_host_like_audit_editor_help(env):
    bin_dir = env["bin"]
    _write_fake_cli(bin_dir / "cursor", editor_help=True)
    rec = env["engine"].audit_provider(
        "cursor",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.noninteractive_status == NoninteractiveStatus.UNSUPPORTED_VERIFIED.value
    assert rec.authentication_status == AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
    assert rec.live_provider_invocations == 0
    # Auth gate still wins as primary per-provider verdict.
    assert rec.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    )


def test_host_system_verdict_priority(env):
    bin_dir = env["bin"]
    _write_fake_cli(bin_dir / "claude", auth="yes", advertise_auth_in_help=True, headless_help=True)
    _write_fake_cli(bin_dir / "codex", auth="yes", advertise_auth_in_help=True, headless_help=True)
    bundle = env["engine"].audit_all(
        project_id="calc-demo",
        providers=["claude_code", "codex"],
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        provider_overrides={
            "claude_code": {
                "synthetic_noninteractive_verified": True,
            },
            "codex": {
                "synthetic_noninteractive_verified": True,
            },
        },
        verify_noninteractive_contract=True,
    )
    assert bundle.live_provider_invocations == 0
    assert bundle.host_system_verdict in (
        HostSystemVerdict.LIVE_SMOKE_READY.value,
        HostSystemVerdict.LIVE_SMOKE_READY_WITH_OPERATOR_AUTH.value,
        HostSystemVerdict.AUTHENTICATION_UNVERIFIED.value,
        HostSystemVerdict.NONINTERACTIVE_UNVERIFIED.value,
        HostSystemVerdict.NO_INDEPENDENT_REVIEWER.value,
        HostSystemVerdict.PROVIDER_NOT_ELIGIBLE.value,
    )
    # With verified auth + synthetic NI, expect live_smoke_ready*
    assert bundle.host_system_verdict.startswith("live_smoke_ready")


def test_host_verdict_auth_unverified_mapping():
    class R:
        provider_id = "cursor"
        discovery_status = "installed"
        authentication_status = AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
        noninteractive_status = NoninteractiveStatus.UNSUPPORTED_VERIFIED.value
        final_readiness_verdict = ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
        implementer_eligibility = RoleEligibility.UNVERIFIED.value
        reviewer_eligibility = RoleEligibility.INELIGIBLE.value

    assert (
        compute_host_system_verdict([R()])
        == HostSystemVerdict.AUTHENTICATION_UNVERIFIED.value
    )


def test_fresh_context_not_true_independence(env):
    bin_dir = env["bin"]
    _write_fake_cli(bin_dir / "claude", auth="yes", advertise_auth_in_help=True)
    import ai_dev_os.provider_readiness_profiles as profiles_mod

    original = profiles_mod.PROFILES["claude_code"]
    profiles_mod.PROFILES["claude_code"] = ProviderReadinessProfile(
        provider_id="claude_code",
        display_name="Claude",
        version_argv=("--version",),
        help_argv=("--help",),
        auth_argv=("auth", "status"),
        auth_probe_mode="profile_only",
        adapter_roles=("implementer", "reviewer"),
        noninteractive_documented=True,
    )
    try:
        bundle = env["engine"].audit_all(
            project_id="calc-demo",
            providers=["claude_code"],
            path_env=str(bin_dir),
            enable_where=False,
            enable_get_command=False,
            provider_overrides={
                "claude_code": {
                    "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
                    "noninteractive_status": NoninteractiveStatus.SUPPORTED_VERIFIED.value,
                    "synthetic_noninteractive_verified": True,
                }
            },
        )
        assert any(
            c.independence_status == "fresh_context_same_provider_only"
            for c in bundle.combinations
        )
        assert not any(c.category == "separate_provider" for c in bundle.combinations)
    finally:
        profiles_mod.PROFILES["claude_code"] = original


def test_token_redaction_still_holds():
    from ai_dev_os.provider_readiness_probes import redact_probe_text

    assert "SECRET" not in redact_probe_text("token=SECRET_TOKEN_VALUE")
    status, _ = interpret_auth_probe(
        type(
            "P",
            (),
            {
                "skipped": False,
                "failure_class": "none",
                "sanitized_output_summary": "logged in",
                "exit_code": 0,
            },
        )()
    )
    assert status == AuthenticationStatus.AUTHENTICATED_VERIFIED
