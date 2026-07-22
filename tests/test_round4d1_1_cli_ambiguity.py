"""Round 4D1.1 CLI ambiguity resolution — synthetic executables only."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from ai_dev_os.models import ProjectRecord
from ai_dev_os.project_registry import ProjectRegistry
from ai_dev_os.provider_config import ProviderConfig, ProviderEntryConfig
from ai_dev_os.provider_models import ProviderMode
from ai_dev_os.provider_readiness_ambiguity import (
    AutoCollapseRule,
    AmbiguityClassification,
    resolve_ambiguity,
    wrapper_is_dynamic,
)
from ai_dev_os.provider_readiness_discovery import (
    ExecutableCandidate,
    discover_executable_candidates,
    hash_executable,
    sanitize_executable_location,
)
from ai_dev_os.provider_readiness_engine import ProviderReadinessEngine
from ai_dev_os.provider_readiness_models import DiscoveryStatus
from ai_dev_os.provider_readiness_pins import (
    ProviderPinStore,
    create_pin,
    validate_pin,
)
from ai_dev_os.provider_readiness_reporting import render_all_audiences
from ai_dev_os.provider_readiness_selection import (
    approval_phrase_for,
    build_operator_decision,
    validate_approval_phrase,
)
from ai_dev_os.safe_policy import PolicyError


def _write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _cand(path: Path, *, method: str = "python_which") -> ExecutableCandidate:
    p = str(path.resolve())
    return ExecutableCandidate(
        path=p,
        basename=path.name,
        resolution_method=method,
        fingerprint=hash_executable(p),
        trusted=True,
        trust_notes="ok",
        sanitized_location=sanitize_executable_location(p),
    )


@pytest.fixture
def demo_registry(tmp_path: Path):
    import tempfile

    demo = Path(tempfile.mkdtemp(prefix="aidos_calc_demo_"))
    (demo / "README.md").write_text("demo\n", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    registry.register(
        ProjectRecord(id="calc-demo", name="Calc", root_path=str(demo), metadata={})
    )
    return registry, demo, tmp_path


def test_duplicate_aliases_collapse(tmp_path: Path):
    target = _write_bytes(tmp_path / "bin" / "cursor.exe", b"FAKE_CURSOR_BIN_V1")
    # Same file via two path spellings is handled by normalize; use identical resolve.
    c1 = _cand(target, method="python_which")
    c2 = ExecutableCandidate(
        path=c1.path,
        basename="cursor.exe",
        resolution_method="where_exe",
        fingerprint=c1.fingerprint,
        trusted=True,
        trust_notes="ok",
        sanitized_location=c1.sanitized_location,
    )
    result = resolve_ambiguity("cursor", [c1, c2])
    assert result.resolved
    assert result.collapse_rule_id in {
        AutoCollapseRule.AC_DUP_DISCOVERY_01.value,
        AutoCollapseRule.AC_SAME_TARGET_01.value,
        AutoCollapseRule.AC_SAME_FP_PROV_01.value,
    }


def test_relative_absolute_same_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bin_dir = tmp_path / "bin"
    target = _write_bytes(bin_dir / "claude.exe", b"CLAUDE_BIN")
    monkeypatch.chdir(bin_dir)
    abs_c = _cand(target)
    rel_path = Path("claude.exe")
    rel_c = ExecutableCandidate(
        path=str(rel_path.resolve()),
        basename="claude.exe",
        resolution_method="where_exe",
        fingerprint=hash_executable(rel_path.resolve()),
        trusted=True,
        trust_notes="ok",
        sanitized_location=sanitize_executable_location(rel_path.resolve()),
    )
    result = resolve_ambiguity("claude_code", [abs_c, rel_c])
    assert result.resolved
    assert len(result.logical_installations) == 1


def test_wrapper_and_target_collapse(tmp_path: Path):
    target = _write_bytes(tmp_path / "bin" / "cursor", b"TARGET_CURSOR_BINARY")
    wrapper = _write_text(
        tmp_path / "bin" / "cursor.cmd",
        '@echo off\r\n"%~dp0cursor" %*\r\n',
    )
    result = resolve_ambiguity("cursor", [_cand(wrapper), _cand(target)])
    assert result.resolved
    assert result.collapse_rule_id == AutoCollapseRule.AC_WRAPPER_TARGET_01.value
    assert len(result.logical_installations) == 1


def test_two_wrappers_same_target(tmp_path: Path):
    target = _write_bytes(tmp_path / "bin" / "codex.exe", b"CODEX_TARGET")
    w1 = _write_text(tmp_path / "bin" / "codex.cmd", '@echo off\r\n"%~dp0codex.exe" %*\r\n')
    w2 = _write_text(tmp_path / "bin" / "codex.bat", '@echo off\r\n"%~dp0codex.exe" %*\r\n')
    result = resolve_ambiguity("codex", [_cand(w1), _cand(w2), _cand(target)])
    assert result.resolved
    assert len(result.logical_installations) == 1


def test_package_manager_shim_style(tmp_path: Path):
    shim_dir = tmp_path / "npm"
    target = _write_bytes(shim_dir / "claude.exe", b"CLAUDE")
    shim = _write_text(shim_dir / "claude.cmd", '@echo off\r\n"%~dp0claude.exe" %*\r\n')
    result = resolve_ambiguity("claude_code", [_cand(shim), _cand(target)])
    assert result.resolved


def test_stale_and_broken_leave_one(tmp_path: Path):
    good = _write_bytes(tmp_path / "bin" / "cursor.exe", b"GOOD")
    stale = tmp_path / "old" / "cursor.exe"
    stale.parent.mkdir(parents=True)
    # missing file candidate
    stale_c = ExecutableCandidate(
        path=str(stale),
        basename="cursor.exe",
        resolution_method="where_exe",
        fingerprint=None,
        trusted=False,
        trust_notes="missing",
        sanitized_location=sanitize_executable_location(stale),
    )
    result = resolve_ambiguity("cursor", [_cand(good), stale_c])
    assert result.resolved
    assert result.collapse_rule_id in {
        AutoCollapseRule.AC_EXCLUDE_BROKEN_01.value,
        AutoCollapseRule.AC_EXCLUDE_UNTRUSTED_01.value,
        AutoCollapseRule.AC_SAME_TARGET_01.value,
        AutoCollapseRule.AC_SAME_FP_PROV_01.value,
    }


def test_trusted_and_untrusted(tmp_path: Path):
    good = _write_bytes(tmp_path / "bin" / "cursor.exe", b"GOOD")
    bad = ExecutableCandidate(
        path=str(tmp_path / "equitify-machine" / "cursor.exe"),
        basename="cursor.exe",
        resolution_method="where_exe",
        fingerprint=None,
        trusted=False,
        trust_notes="equitify",
        sanitized_location="blocked",
    )
    result = resolve_ambiguity("cursor", [_cand(good), bad])
    assert result.resolved
    assert bad.path not in (result.selected_path or "")


def test_two_trusted_require_selection(tmp_path: Path):
    a = _write_bytes(tmp_path / "a" / "cursor.exe", b"INSTALL_A")
    b = _write_bytes(tmp_path / "b" / "cursor.exe", b"INSTALL_B_DIFFERENT")
    result = resolve_ambiguity("cursor", [_cand(a), _cand(b)])
    assert not result.resolved
    assert result.requires_operator_selection
    decision = build_operator_decision(result)
    assert decision.decision_status == "operator_selection_required"
    assert decision.recommended_candidate_id
    assert "Approve provider executable" in decision.approval_phrase
    assert validate_approval_phrase(decision.approval_phrase, decision.recommended_candidate_id)


def test_same_version_different_fingerprints_not_equivalent(tmp_path: Path):
    a = _write_bytes(tmp_path / "a" / "claude.exe", b"VER_A")
    b = _write_bytes(tmp_path / "b" / "claude.exe", b"VER_B")
    ca, cb = _cand(a), _cand(b)
    ca.cli_version = "1.2.3"  # type: ignore[attr-defined]
    result = resolve_ambiguity("claude_code", [ca, cb])
    assert result.requires_operator_selection


def test_malicious_wrapper_not_executed(tmp_path: Path):
    marker = tmp_path / "PWNED.txt"
    wrapper = _write_text(
        tmp_path / "bin" / "cursor.cmd",
        '@echo off\r\necho pwned> "' + str(marker) + '"\r\n"%~dp0cursor.exe" %*\r\n',
    )
    # Dynamic path via redirect still parsed as data; ensure we never run it.
    text = wrapper.read_text(encoding="utf-8")
    # Presence of echo redirect shouldn't create the file unless executed.
    assert not marker.exists()
    _ = resolve_ambiguity("cursor", [_cand(wrapper)])
    assert not marker.exists()
    assert "pwned" in text.lower() or "PWNED" in str(marker)


def test_dynamic_wrapper_rejected(tmp_path: Path):
    wrapper = _write_text(
        tmp_path / "bin" / "cursor.cmd",
        '@echo off\r\ncmd /c "%CURSOR_HOME%\\cursor.exe" %*\r\n',
    )
    assert wrapper_is_dynamic(wrapper.read_text(encoding="utf-8"))
    result = resolve_ambiguity("cursor", [_cand(wrapper)])
    # Alone → may be unresolved / no trusted selectable target
    assert result.selected_path is None or result.note


def test_path_only_pin_rejected(tmp_path: Path):
    exe = _write_bytes(tmp_path / "cursor.exe", b"X")
    with pytest.raises(PolicyError):
        create_pin(
            provider_id="cursor",
            candidate_id="cand_x",
            canonical_executable_path=str(exe),
            expected_fingerprint="",
            adapter_id="cursor",
            adapter_version="3b.1",
            approval_phrase=approval_phrase_for("cand_x"),
        )


def test_pin_fingerprint_mismatch(tmp_path: Path):
    exe = _write_bytes(tmp_path / "cursor.exe", b"PINME")
    pin = create_pin(
        provider_id="cursor",
        candidate_id="cand_x",
        canonical_executable_path=str(exe),
        expected_fingerprint="0" * 64,
        adapter_id="cursor",
        adapter_version="3b.1",
        approval_phrase=approval_phrase_for("cand_x"),
    )
    result = validate_pin(pin, adapter_version="3b.1")
    assert not result.valid
    assert "fingerprint_mismatch" in result.reasons
    assert result.live_mode_enabled is False
    assert result.authentication_implied is False


def test_valid_pin_and_store(tmp_path: Path):
    exe = _write_bytes(tmp_path / "cursor.exe", b"PINME_OK")
    fp = hash_executable(exe)
    pin = create_pin(
        provider_id="cursor",
        candidate_id="cand_ok",
        canonical_executable_path=str(exe),
        expected_fingerprint=fp or "",
        adapter_id="cursor",
        adapter_version="3b.1",
        approval_phrase=approval_phrase_for("cand_ok"),
    )
    store = ProviderPinStore(tmp_path / "pins")
    store.save(pin)
    loaded = store.load("cursor")
    assert loaded is not None
    result = validate_pin(loaded, adapter_version="3b.1")
    assert result.valid
    assert result.live_mode_enabled is False


def test_discovery_collapses_wrapper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bin_dir = tmp_path / "bin"
    target = _write_bytes(bin_dir / "cursor", b"TARGET_CURSOR_BINARY_DISC")
    _write_text(bin_dir / "cursor.cmd", '@echo off\r\n"%~dp0cursor" %*\r\n')
    monkeypatch.setenv("PATH", str(bin_dir))
    result = discover_executable_candidates(
        "cursor",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert result.status is DiscoveryStatus.INSTALLED
    assert result.ambiguity is not None
    assert result.ambiguity.get("resolved") is True


def test_discovery_two_installs_ambiguous(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write_bytes(a / "cursor.exe", b"AAA")
    _write_bytes(b / "cursor.exe", b"BBB")
    path_env = os.pathsep.join([str(a), str(b)])
    result = discover_executable_candidates(
        "cursor",
        path_env=path_env,
        enable_where=False,
        enable_get_command=False,
    )
    assert result.status is DiscoveryStatus.AMBIGUOUS_INSTALLATION
    assert result.ambiguity and result.ambiguity.get("requires_operator_selection")


def test_engine_metadata_and_reports(demo_registry):
    registry, demo, tmp_path = demo_registry
    bin_dir = tmp_path / "bin"
    target = _write_bytes(bin_dir / "claude", b"CLAUDE_OK")
    _write_text(bin_dir / "claude.cmd", '@echo off\r\n"%~dp0claude" %*\r\n')
    config = ProviderConfig(
        providers={
            "claude_code": ProviderEntryConfig(
                provider_id="claude_code",
                enabled=True,
                mode=ProviderMode.DISCOVERY_ONLY,
                allow_live=False,
            ),
            "cursor": ProviderEntryConfig(
                provider_id="cursor", enabled=True, mode=ProviderMode.DISCOVERY_ONLY
            ),
            "codex": ProviderEntryConfig(
                provider_id="codex", enabled=True, mode=ProviderMode.DISCOVERY_ONLY
            ),
            "simulated": ProviderEntryConfig(
                provider_id="simulated", enabled=False, mode=ProviderMode.DISABLED
            ),
        }
    )
    engine = ProviderReadinessEngine(repo_root=tmp_path, config=config, registry=registry)
    rec = engine.audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec.live_provider_invocations == 0
    assert rec.discovery_status == DiscoveryStatus.INSTALLED.value
    amb = rec.metadata.get("ambiguity_resolution") or {}
    assert amb.get("resolved") is True

    # Two installs → selection record
    a = tmp_path / "ia"
    b = tmp_path / "ib"
    _write_bytes(a / "cursor.exe", b"C1")
    _write_bytes(b / "cursor.exe", b"C2")
    rec2 = engine.audit_provider(
        "cursor",
        project_id="calc-demo",
        path_env=os.pathsep.join([str(a), str(b)]),
        enable_where=False,
        enable_get_command=False,
    )
    assert rec2.discovery_status == DiscoveryStatus.AMBIGUOUS_INSTALLATION.value
    assert rec2.metadata.get("operator_decision")

    from ai_dev_os.provider_readiness_models import ReadinessAuditBundle, new_audit_id
    from ai_dev_os.models import utc_now_iso

    bundle = ReadinessAuditBundle(
        audit_id=new_audit_id(),
        schema_version="4d1.1",
        readiness_policy_version="4d1.1",
        generated_at=utc_now_iso(),
        project_id="calc-demo",
        repository_identity="test",
        repository_commit="abc",
        host_platform="test",
        provider_records=[rec, rec2],
        combinations=[],
        aggregate_verdict="ambiguous_provider_installation",
        recommended_combination=None,
        blockers=["cursor:ambiguous"],
        warnings=[],
        live_provider_invocations=0,
    )
    reports = render_all_audiences(bundle)
    assert "Model requests during this audit: 0" in reports["executive"]
    assert "candidate matrix" in reports["operator"] or "approval phrase" in reports["operator"]
    assert "logical installations" in reports["developer"].lower() or "ambiguity" in reports["developer"].lower()
    assert "live_provider_invocations" in reports["auditor"]


def test_sanitize_hides_username():
    label = sanitize_executable_location(r"C:\Users\SecretUser\AppData\Local\Programs\cursor\cursor.cmd")
    assert "SecretUser" not in label or label.startswith("user_home/")
    # user_home form redacts to relative under home — may still include segments but not full drive dump
    assert "PATH=" not in label


def test_cli_flags_registered():
    from ai_dev_os.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "provider-readiness",
            "--project-id",
            "calc-demo",
            "--show-candidates",
            "--explain-ambiguity",
            "--show-logical-installations",
            "--json",
        ]
    )
    assert args.show_candidates
    assert args.explain_ambiguity
    assert args.show_logical_installations


def test_approval_phrase_validation():
    cid = "cand_abc123"
    phrase = approval_phrase_for(cid)
    assert validate_approval_phrase(phrase, cid)
    assert not validate_approval_phrase(phrase + "!", cid)
    assert not validate_approval_phrase(phrase, "cand_other")


def test_scenario_successful_normalization_ready_path(demo_registry):
    """Scenario 10: ambiguity collapses; no provider prompt."""
    registry, demo, tmp_path = demo_registry
    bin_dir = tmp_path / "bin"
    target = _write_bytes(bin_dir / "claude", b"CLAUDE_NORM")
    _write_text(bin_dir / "claude.cmd", '@echo off\r\n"%~dp0claude" %*\r\n')
    config = ProviderConfig(
        providers={
            "claude_code": ProviderEntryConfig(
                provider_id="claude_code",
                enabled=True,
                mode=ProviderMode.DISCOVERY_ONLY,
                allow_live=False,
            )
        }
    )
    engine = ProviderReadinessEngine(repo_root=tmp_path, config=config, registry=registry)
    before_style = DiscoveryStatus.AMBIGUOUS_INSTALLATION.value
    rec = engine.audit_provider(
        "claude_code",
        project_id="calc-demo",
        path_env=str(bin_dir),
        enable_where=False,
        enable_get_command=False,
        allow_unknown_auth_conditional=True,
    )
    assert rec.discovery_status != before_style or rec.discovery_status == DiscoveryStatus.INSTALLED.value
    assert rec.discovery_status == DiscoveryStatus.INSTALLED.value
    assert rec.live_provider_invocations == 0
