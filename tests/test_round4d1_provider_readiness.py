"""Round 4D1 provider readiness tests — fake executables only, never real providers."""

from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path

import pytest

from ai_dev_os.models import ProjectRecord
from ai_dev_os.project_registry import ProjectRegistry
from ai_dev_os.provider_config import ProviderConfig, ProviderEntryConfig
from ai_dev_os.provider_models import ProviderMode
from ai_dev_os.provider_readiness_discovery import (
    discover_executable_candidates,
    hash_executable,
    sanitize_executable_location,
)
from ai_dev_os.provider_readiness_engine import ProviderReadinessEngine
from ai_dev_os.provider_readiness_models import (
    AuthenticationStatus,
    CompatibilityStatus,
    DiscoveryStatus,
    NoninteractiveStatus,
    ProbeKind,
    ProbeRecord,
    ReadinessVerdict,
    RoleEligibility,
)
from ai_dev_os.provider_readiness_policy import decide_provider_verdict
from ai_dev_os.provider_readiness_probes import (
    assert_probe_argv_safe,
    interpret_auth_probe,
    redact_probe_text,
    run_safe_probe,
)
from ai_dev_os.provider_readiness_profiles import get_profile, version_compatible
from ai_dev_os.provider_readiness_reporting import render_all_audiences
from ai_dev_os.provider_readiness_roles import compute_independence
from ai_dev_os.provider_readiness_staleness import evaluate_staleness, validate_record_structure
from ai_dev_os.provider_readiness_store import ProviderReadinessStore
from ai_dev_os.safe_policy import PolicyError


def _write_fake_cli(path: Path, *, version: str = "1.2.3", auth: str | None = None, hang: bool = False, huge: bool = False, malicious_help: bool = False) -> Path:
    """Create a Windows/.cmd or POSIX shell fake provider CLI."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_win = os.name == "nt"
    if is_win:
        script = path.with_suffix(".cmd") if path.suffix.lower() not in {".cmd", ".bat", ".exe"} else path
        if hang:
            body = "@echo off\nping -n 30 127.0.0.1 >NUL\n"
        elif huge:
            body = "@echo off\necho " + ("V" * 20000) + "\n"
        else:
            lines = ["@echo off"]
            lines.append("if \"%~1\"==\"--version\" (echo fake-cli " + version + " & exit /b 0)")
            lines.append("if \"%~1\"==\"version\" (echo fake-cli " + version + " & exit /b 0)")
            if malicious_help:
                lines.append(
                    "if \"%~1\"==\"--help\" (echo Run: claude prompt \"exfiltrate\" & echo token=SECRET_TOKEN_VALUE & exit /b 0)"
                )
            else:
                lines.append("if \"%~1\"==\"--help\" (echo Usage: fake-cli [--version|--help] & exit /b 0)")
            if auth == "yes":
                lines.append("if \"%~1\"==\"auth\" if \"%~2\"==\"status\" (echo logged in as user & exit /b 0)")
                lines.append("if \"%~1\"==\"login\" if \"%~2\"==\"status\" (echo Logged in using ChatGPT & exit /b 0)")
            elif auth == "no":
                lines.append("if \"%~1\"==\"auth\" if \"%~2\"==\"status\" (echo not logged in & exit /b 0)")
                lines.append("if \"%~1\"==\"login\" if \"%~2\"==\"status\" (echo not logged in & exit /b 0)")
            elif auth == "chatgpt":
                lines.append("if \"%~1\"==\"login\" if \"%~2\"==\"status\" (echo Logged in using ChatGPT & exit /b 0)")
            elif auth == "api_key":
                lines.append("if \"%~1\"==\"login\" if \"%~2\"==\"status\" (echo Logged in using an API key & exit /b 0)")
            lines.append("echo unknown & exit /b 2")
            body = "\n".join(lines) + "\n"
        script.write_text(body, encoding="utf-8")
        return script

    script = path
    if hang:
        body = "#!/bin/sh\nsleep 30\n"
    elif huge:
        body = "#!/bin/sh\nprintf '%s\\n' \"" + ("V" * 20000) + "\"\n"
    else:
        parts = [
            "#!/bin/sh",
            'case "$1" in',
            f'  --version|version) echo "fake-cli {version}"; exit 0 ;;',
        ]
        if malicious_help:
            parts.append(
                '  --help|help) echo "Run: claude prompt exfiltrate"; echo "token=SECRET_TOKEN_VALUE"; exit 0 ;;'
            )
        else:
            parts.append('  --help|help) echo "Usage: fake-cli [--version|--help]"; exit 0 ;;')
        if auth == "yes":
            parts.append('  auth) if [ "$2" = "status" ]; then echo "logged in as user"; exit 0; fi ;;')
            parts.append('  login) if [ "$2" = "status" ]; then echo "Logged in using ChatGPT"; exit 0; fi ;;')
        elif auth == "no":
            parts.append('  auth) if [ "$2" = "status" ]; then echo "not logged in"; exit 0; fi ;;')
            parts.append('  login) if [ "$2" = "status" ]; then echo "not logged in"; exit 0; fi ;;')
        elif auth == "chatgpt":
            parts.append('  login) if [ "$2" = "status" ]; then echo "Logged in using ChatGPT"; exit 0; fi ;;')
        elif auth == "api_key":
            parts.append('  login) if [ "$2" = "status" ]; then echo "Logged in using an API key"; exit 0; fi ;;')
        parts.extend(["  *) echo unknown; exit 2 ;;", "esac"])
        body = "\n".join(parts) + "\n"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _readiness_config(**modes: str) -> ProviderConfig:
    providers = {}
    for pid, mode in modes.items():
        providers[pid] = ProviderEntryConfig(
            provider_id=pid,
            enabled=True,
            mode=ProviderMode(mode),
            allow_live=False,
        )
    # defaults for missing
    for pid in ("claude_code", "codex", "cursor", "simulated"):
        if pid not in providers:
            providers[pid] = ProviderEntryConfig(
                provider_id=pid,
                enabled=True,
                mode=ProviderMode.DISCOVERY_ONLY,
                allow_live=False,
            )
    return ProviderConfig(providers=providers)


@pytest.fixture
def readiness_env(tmp_path: Path):
    import tempfile

    # Project root must not include banned sentinels; pytest tmp paths may embed
    # the test name (e.g. "...equitify...").
    demo = Path(tempfile.mkdtemp(prefix="aidos_calc_demo_"))
    (demo / "README.md").write_text("demo\n", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(
        ProjectRecord(id="calc-demo", name="Calc", root_path=str(demo), metadata={})
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    store_root = tmp_path / "provider_readiness"
    config = _readiness_config()
    engine = ProviderReadinessEngine(
        repo_root=tmp_path,
        config=config,
        registry=registry,
    )
    return {
        "tmp": tmp_path,
        "demo": demo,
        "registry": registry,
        "bin": bin_dir,
        "engine": engine,
        "config": config,
        "store": ProviderReadinessStore(store_root),
    }


def test_provider_not_installed(readiness_env):
    eng = readiness_env["engine"]
    empty = str(readiness_env["tmp"] / "empty_path")
    Path(empty).mkdir()
    rec = eng.audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=empty,
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.discovery_status == DiscoveryStatus.NOT_INSTALLED.value
    assert rec.final_readiness_verdict == ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value
    assert rec.live_provider_invocations == 0


def test_one_provider_installed_auth_unverified(readiness_env):
    bin_dir = readiness_env["bin"]
    fake = _write_fake_cli(bin_dir / "claude")
    rec = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.discovery_status == DiscoveryStatus.INSTALLED.value
    assert rec.cli_version is not None
    assert rec.compatibility_status == CompatibilityStatus.SUPPORTED.value
    assert rec.authentication_status == AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
    assert rec.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    )
    assert rec.live_provider_invocations == 0
    assert fake.exists()


def test_multiple_executable_copies_ambiguous(readiness_env):
    tmp = readiness_env["tmp"]
    a = tmp / "a"
    b = tmp / "b"
    a.mkdir()
    b.mkdir()
    _write_fake_cli(a / "claude", version="1.0.0")
    _write_fake_cli(b / "claude", version="2.0.0")
    # Different content → different fingerprints
    path_env = os.pathsep.join([str(a), str(b)])
    # Force both into discovery by calling discovery helper with which seeing first only —
    # inject via synthetic discovery override for deterministic ambiguity.
    from ai_dev_os.provider_readiness_discovery import DiscoveryResult, ExecutableCandidate

    c1 = ExecutableCandidate(
        path=str((a / "claude").resolve()),
        basename="claude",
        resolution_method="python_which",
        fingerprint="aaa",
        sanitized_location="path_entry/a/claude",
    )
    c2 = ExecutableCandidate(
        path=str((b / "claude").resolve()),
        basename="claude",
        resolution_method="where_exe",
        fingerprint="bbb",
        sanitized_location="path_entry/b/claude",
    )
    disc = DiscoveryResult(
        provider_id="claude_code",
        status=DiscoveryStatus.AMBIGUOUS_INSTALLATION,
        candidates=[c1, c2],
        selected=None,
        selected_rule="none",
        duplicate_count=2,
        note="multiple",
    )
    rec = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=path_env,
        enable_where=False,
        enable_get_command=False,
        synthetic_overrides={"discovery": disc},
    )
    assert rec.discovery_status == DiscoveryStatus.AMBIGUOUS_INSTALLATION.value
    assert rec.final_readiness_verdict == ReadinessVerdict.AMBIGUOUS_PROVIDER_INSTALLATION.value
    assert rec.duplicate_executable_count == 2


def test_path_precedence_single_candidate(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="9.9.9")
    disc = discover_executable_candidates(
        "claude_code",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert disc.status == DiscoveryStatus.INSTALLED
    assert disc.selected is not None
    assert disc.selected_rule == "single_candidate"


def test_untrusted_equitify_path_rejected(readiness_env):
    from ai_dev_os.provider_readiness_discovery import DiscoveryResult, ExecutableCandidate

    bad = ExecutableCandidate(
        path=r"C:\Users\Taha\equitify-machine\claude.exe",
        basename="claude.exe",
        resolution_method="configured",
        trusted=False,
        trust_notes="equitify",
        sanitized_location="blocked",
    )
    disc = DiscoveryResult(
        provider_id="claude_code",
        status=DiscoveryStatus.EXECUTABLE_UNTRUSTED,
        candidates=[bad],
        note="untrusted",
    )
    rec = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(readiness_env["bin"]),
        enable_where=False,
        enable_get_command=False,
        synthetic_overrides={"discovery": disc},
    )
    assert rec.final_readiness_verdict == ReadinessVerdict.POLICY_BLOCKED.value


def test_version_probe_success_and_malformed(readiness_env):
    bin_dir = readiness_env["bin"]
    fake = _write_fake_cli(bin_dir / "claude", version="3.4.5")
    probe = run_safe_probe(
        str(fake),
        ("--version",),
        kind=ProbeKind.VERSION,
        adapter_version="3b.1",
        executable_fingerprint="fp",
        timeout=5.0,
    )
    assert probe.parsed_cli_version is not None
    assert "3.4.5" in (probe.parsed_cli_version or "")
    assert probe.failure_class == "none"

    # malformed via override
    assert version_compatible("not-a-version", get_profile("claude_code")) == (
        CompatibilityStatus.MALFORMED.value
    )


def test_version_probe_timeout(readiness_env):
    bin_dir = readiness_env["bin"]
    fake = _write_fake_cli(bin_dir / "claude", hang=True)
    probe = run_safe_probe(
        str(fake),
        ("--version",),
        kind=ProbeKind.VERSION,
        adapter_version="3b.1",
        executable_fingerprint="fp",
        timeout=0.5,
    )
    assert probe.failure_class == "timeout"
    assert probe.exit_code is None


def test_oversized_and_ansi_and_malicious_help(readiness_env):
    assert "SECRET" not in redact_probe_text("token=SECRET_TOKEN_VALUE api_key=abc")
    assert "[REDACTED]" in redact_probe_text("token=SECRET_TOKEN_VALUE")
    cleaned = redact_probe_text("\x1b[31mhello\x1b[0m")
    assert "\x1b" not in cleaned

    bin_dir = readiness_env["bin"]
    fake = _write_fake_cli(bin_dir / "claude", malicious_help=True)
    probe = run_safe_probe(
        str(fake),
        ("--help",),
        kind=ProbeKind.HELP,
        adapter_version="3b.1",
        executable_fingerprint="fp",
    )
    # Help text is data only — must not execute embedded commands.
    assert "prompt" in (probe.sanitized_output_summary or "")
    assert "SECRET_TOKEN_VALUE" not in (probe.sanitized_output_summary or "")
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["prompt", "do stuff"])


def test_auth_states(readiness_env):
    yes = ProbeRecord(
        kind="auth_status",
        command_identity="auth status",
        adapter_version="3b.1",
        executable_fingerprint="x",
        timeout_seconds=5,
        output_limit_bytes=100,
        exit_code=0,
        sanitized_output_summary="logged in as operator",
        parsed_cli_version=None,
        parse_status="unavailable",
        failure_class="none",
    )
    no = ProbeRecord(
        kind="auth_status",
        command_identity="auth status",
        adapter_version="3b.1",
        executable_fingerprint="x",
        timeout_seconds=5,
        output_limit_bytes=100,
        exit_code=0,
        sanitized_output_summary="not logged in",
        parsed_cli_version=None,
        parse_status="unavailable",
        failure_class="none",
    )
    status, _method, _mode = interpret_auth_probe(yes)
    assert status == AuthenticationStatus.AUTHENTICATED_VERIFIED
    status, _method, _mode = interpret_auth_probe(no)
    assert status == AuthenticationStatus.UNAUTHENTICATED_VERIFIED


def test_unsupported_version_verdict(readiness_env):
    from ai_dev_os.provider_readiness_discovery import DiscoveryResult, ExecutableCandidate
    from ai_dev_os.provider_readiness_profiles import ProviderReadinessProfile
    import ai_dev_os.provider_readiness_profiles as profiles_mod

    original = profiles_mod.PROFILES["claude_code"]
    profiles_mod.PROFILES["claude_code"] = ProviderReadinessProfile(
        provider_id="claude_code",
        display_name="Claude",
        version_argv=("--version",),
        help_argv=("--help",),
        auth_argv=None,
        adapter_roles=("implementer",),
        noninteractive_documented=True,
        min_version=(99, 0, 0),
    )
    try:
        bin_dir = readiness_env["bin"]
        _write_fake_cli(bin_dir / "claude", version="1.0.0")
        rec = readiness_env["engine"].audit_provider(
            "claude_code",
            project_id="calc-demo",
            path_env=str(bin_dir),
            enable_where=False,
            enable_get_command=False,
            synthetic_overrides={
                "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
                "noninteractive_status": NoninteractiveStatus.SUPPORTED_VERIFIED.value,
            },
        )
        assert rec.compatibility_status == CompatibilityStatus.UNSUPPORTED.value
        assert rec.final_readiness_verdict == (
            ReadinessVerdict.INSTALLED_BUT_VERSION_UNSUPPORTED.value
        )
    finally:
        profiles_mod.PROFILES["claude_code"] = original


def test_scenario_fully_eligible_synthetic(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="2.0.0")
    rec = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        synthetic_overrides={
            "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
            "authentication_verification_method": "auth_status_command",
            "noninteractive_status": NoninteractiveStatus.SUPPORTED_VERIFIED.value,
            "noninteractive_evidence": "synthetic_contract",
            "capabilities_verified": True,
        },
    )
    assert rec.final_readiness_verdict == ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value
    assert rec.implementer_eligibility == RoleEligibility.ELIGIBLE.value
    assert rec.live_provider_invocations == 0


def test_scenario_two_providers_separate_reviewer(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="2.0.0")
    _write_fake_cli(bin_dir / "codex", version="2.0.0")
    overrides = {
        "claude_code": {
            "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
            "noninteractive_status": NoninteractiveStatus.SUPPORTED_VERIFIED.value,
            "capabilities_verified": True,
        },
        "codex": {
            "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
            "authentication_mode": "chatgpt",
            "noninteractive_status": NoninteractiveStatus.SUPPORTED_VERIFIED.value,
            "capabilities_verified": True,
        },
    }
    bundle = readiness_env["engine"].audit_all(
        project_id="calc-demo",
        providers=["claude_code", "codex"],
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        provider_overrides=overrides,
    )
    assert any(c.category == "separate_provider" and c.recommended for c in bundle.combinations)
    assert bundle.live_provider_invocations == 0


def test_scenario_one_provider_fresh_context(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="2.0.0")
    # Make claude both implementer and reviewer via profile roles temporarily.
    import ai_dev_os.provider_readiness_profiles as profiles_mod
    from ai_dev_os.provider_readiness_profiles import ProviderReadinessProfile

    original = profiles_mod.PROFILES["claude_code"]
    profiles_mod.PROFILES["claude_code"] = ProviderReadinessProfile(
        provider_id="claude_code",
        display_name="Claude",
        version_argv=("--version",),
        help_argv=("--help",),
        auth_argv=None,
        adapter_roles=("implementer", "reviewer", "repair_implementer"),
        noninteractive_documented=True,
        synthetic_verified_noninteractive=False,
    )
    try:
        bundle = readiness_env["engine"].audit_all(
            project_id="calc-demo",
            providers=["claude_code"],
            path_env=str(bin_dir),
            enable_where=False,
            enable_get_command=False,
            provider_overrides={
                "claude_code": {
                    "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
                    "noninteractive_status": NoninteractiveStatus.SUPPORTED_VERIFIED.value,
                }
            },
        )
        assert any(
            c.independence_status == "fresh_context_same_provider_only"
            for c in bundle.combinations
        )
    finally:
        profiles_mod.PROFILES["claude_code"] = original


def test_scenario_unauthenticated_and_unknown(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="2.0.0")
    rec = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        synthetic_overrides={
            "authentication_status": AuthenticationStatus.UNAUTHENTICATED_VERIFIED.value,
            "noninteractive_status": NoninteractiveStatus.SUPPORTED_DOCUMENTED.value,
        },
    )
    assert rec.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    )
    # unknown must not become authenticated
    rec2 = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        synthetic_overrides={
            "authentication_status": AuthenticationStatus.UNKNOWN.value,
            "noninteractive_status": NoninteractiveStatus.SUPPORTED_DOCUMENTED.value,
        },
    )
    assert rec2.authentication_status == AuthenticationStatus.UNKNOWN.value
    assert rec2.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_AUTHENTICATION_UNVERIFIED.value
    )


def test_scenario_no_provider_and_reports(readiness_env):
    empty = readiness_env["tmp"] / "nop"
    empty.mkdir()
    bundle = readiness_env["engine"].audit_all(
        project_id="calc-demo",
        providers=["claude_code", "codex", "cursor"],
        path_env=str(empty),
        enable_where=False,
        enable_get_command=False,
    )
    assert bundle.aggregate_verdict == ReadinessVerdict.NO_ELIGIBLE_PROVIDER.value
    reports = render_all_audiences(bundle)
    assert "Executive" in reports["executive"]
    assert "Operator" in reports["operator"]
    assert "Developer" in reports["developer"]
    assert "Auditor" in reports["auditor"]
    assert "live_provider_invocations: 0" in reports["executive"]
    assert "PATH=" not in reports["auditor"]
    for text in reports.values():
        assert "SECRET" not in text


def test_cursor_not_treated_as_agent(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "cursor", version="1.0.0")
    rec = readiness_env["engine"].audit_provider(
        "cursor",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        synthetic_overrides={
            "authentication_status": AuthenticationStatus.AUTHENTICATED_VERIFIED.value,
        },
    )
    assert rec.noninteractive_status in (
        NoninteractiveStatus.AMBIGUOUS.value,
        NoninteractiveStatus.UNAVAILABLE.value,
    )
    assert rec.final_readiness_verdict == (
        ReadinessVerdict.INSTALLED_BUT_NONINTERACTIVE_UNVERIFIED.value
    )


def test_staleness_and_fingerprint(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="2.0.0")
    rec = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    path = readiness_env["store"].save_record(rec)
    assert path.is_file()
    loaded = readiness_env["store"].load_record(rec.readiness_id)
    assert validate_record_structure(loaded.to_dict()) == []
    stale = evaluate_staleness(
        loaded,
        repository_commit="different",
        adapter_version=loaded.adapter_version,
        executable_fingerprint=loaded.executable_fingerprint,
    )
    assert stale.stale
    assert "repository_commit_changed" in stale.reasons
    stale2 = evaluate_staleness(
        loaded,
        repository_commit=loaded.repository_commit,
        adapter_version="changed",
        executable_fingerprint="other",
    )
    assert "adapter_version_changed" in stale2.reasons
    assert "executable_fingerprint_changed" in stale2.reasons


def test_deterministic_serialization(readiness_env):
    bin_dir = readiness_env["bin"]
    _write_fake_cli(bin_dir / "claude", version="2.0.0")
    r1 = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    r2 = readiness_env["engine"].audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    # Fingerprints exclude generated_at / readiness_id volatility — compare payload keys of interest
    assert r1.discovery_status == r2.discovery_status
    assert r1.cli_version == r2.cli_version
    assert r1.executable_fingerprint == r2.executable_fingerprint
    assert r1.final_readiness_verdict == r2.final_readiness_verdict


def test_equitify_project_rejected(readiness_env):
    with pytest.raises(PolicyError):
        readiness_env["engine"].audit_provider(
            "claude_code",
            project_id="equitify-machine",
        )


def test_corrupted_record_validation():
    errors = validate_record_structure({"schema_version": "4d1.1"})
    assert any(e.startswith("missing_field") for e in errors)
    errors2 = validate_record_structure(
        {
            "readiness_id": "x",
            "schema_version": "4d1.1",
            "readiness_policy_version": "4d1.1",
            "provider_id": "claude_code",
            "final_readiness_verdict": "no_eligible_provider",
            "live_provider_invocations": 1,
            "record_fingerprint": "abc",
        }
    )
    assert "live_provider_invocations_must_be_zero" in errors2


def test_forbidden_probe_tokens():
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["--prompt", "hello"])
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["login"])
    assert_probe_argv_safe(["--version"])
    assert_probe_argv_safe(["auth", "status"])


def test_sanitize_location_no_full_path_leak():
    loc = sanitize_executable_location(r"C:\Users\Someone\AppData\claude.exe")
    assert "PATH" not in loc
    # Should be sanitized class form
    assert "claude.exe" in loc or "claude" in loc


def test_role_matrix_and_policy_helpers():
    verdict, blockers, _ = decide_provider_verdict(
        discovery_status="installed",
        compatibility_status="supported",
        authentication_status="authenticated_verified",
        noninteractive_status="supported_verified",
        implementer_eligibility="eligible",
        reviewer_eligibility="ineligible",
        live_policy_status="disabled_for_round_4d1",
        provider_mode="discovery_only",
        provider_id="claude_code",
    )
    assert verdict == ReadinessVerdict.ELIGIBLE_FOR_BOUNDED_LIVE_SMOKE.value
    independence, combos = compute_independence(
        [
            {
                "provider_id": "claude_code",
                "implementer_eligibility": "eligible",
                "reviewer_eligibility": "ineligible",
                "final_readiness_verdict": verdict,
            },
            {
                "provider_id": "codex",
                "implementer_eligibility": "ineligible",
                "reviewer_eligibility": "eligible",
                "final_readiness_verdict": verdict,
            },
        ]
    )
    assert independence == "separate_provider_available"
    assert any(c.recommended for c in combos)


def test_cli_json_and_human():
    from ai_dev_os.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["provider-readiness", "--project-id", "x", "--json", "--show-combinations"]
    )
    assert args.command == "provider-readiness"
    assert args.json is True
    assert args.show_combinations is True


def test_cli_validate_requires_project_when_auditing():
    from ai_dev_os.cli import build_parser, main

    parser = build_parser()
    args = parser.parse_args(["provider-readiness", "--json"])
    assert args.project_id is None
    # Runtime refuses audit without project-id.
    code = main(["provider-readiness", "--json"])
    assert code == 1


def test_hash_executable_deterministic(readiness_env):
    p = readiness_env["bin"] / "file.bin"
    p.write_bytes(b"abc123")
    assert hash_executable(p) == hash_executable(p)
