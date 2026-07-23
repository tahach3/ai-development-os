"""Round 4D1.3 Codex headless-provider readiness — synthetic fixtures only."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from ai_dev_os.provider_readiness_auth import resolve_auth_probe_plan, scan_help_for_auth_status
from ai_dev_os.provider_readiness_noninteractive import (
    assess_noninteractive_contract,
    build_synthetic_headless_argv,
)
from ai_dev_os.provider_readiness_policy import decide_provider_verdict
from ai_dev_os.provider_readiness_probes import (
    assert_probe_argv_safe,
    interpret_auth_probe,
    interpret_authentication_mode,
)
from ai_dev_os.provider_readiness_profiles import get_profile
from ai_dev_os.provider_readiness_roles import compute_independence
from ai_dev_os.providers.codex_env import (
    build_codex_child_environment,
    report_codex_env_presence,
)
from ai_dev_os.providers.codex_events import (
    build_future_codex_exec_argv,
    normalize_codex_jsonl,
)
from ai_dev_os.safe_policy import PolicyError


def test_login_status_allowlisted_but_bare_login_forbidden():
    assert_probe_argv_safe(["login", "status"])
    assert_probe_argv_safe(["exec", "--help"])
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["login"])
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["exec"])
    with pytest.raises(PolicyError):
        assert_probe_argv_safe(["exec", "reply PING"])


def test_help_advertises_login_status():
    adv, argv, note = scan_help_for_auth_status(
        "Commands:\n  login status   Show login status\n  login          Sign in"
    )
    assert adv is True
    assert argv == ("login", "status")
    plan = resolve_auth_probe_plan(
        profile_auth_argv=("login", "status"),
        auth_probe_mode="profile_only",
        help_text=None,
    )
    assert plan.runnable and plan.argv == ("login", "status")


def test_auth_mode_chatgpt_vs_api_key():
    assert interpret_authentication_mode("Logged in using ChatGPT") == "chatgpt"
    assert interpret_authentication_mode("Logged in using an API key") == "api_key"
    probe = type(
        "P",
        (),
        {
            "skipped": False,
            "failure_class": "none",
            "exit_code": 0,
            "sanitized_output_summary": "Logged in using ChatGPT",
        },
    )()
    status, method, mode = interpret_auth_probe(probe)
    assert status.value == "authenticated_verified"
    assert mode == "chatgpt"
    assert method == "auth_status_command"


def test_api_key_mode_blocks_eligibility():
    verdict, blockers, _ = decide_provider_verdict(
        discovery_status="installed",
        compatibility_status="supported",
        authentication_status="authenticated_verified",
        noninteractive_status="supported_documented",
        implementer_eligibility="eligible",
        reviewer_eligibility="eligible",
        live_policy_status="disabled_for_round_4d1",
        provider_mode="discovery_only",
        provider_id="codex",
        authentication_mode="api_key",
    )
    assert verdict == "installed_but_authentication_unverified"
    assert any("api_key" in b for b in blockers)


def test_chatgpt_mode_codex_conditional_eligible():
    verdict, blockers, warnings = decide_provider_verdict(
        discovery_status="installed",
        compatibility_status="supported",
        authentication_status="authenticated_verified",
        noninteractive_status="supported_documented",
        implementer_eligibility="eligible",
        reviewer_eligibility="eligible",
        live_policy_status="disabled_for_round_4d1",
        provider_mode="discovery_only",
        provider_id="codex",
        authentication_mode="chatgpt",
    )
    assert verdict == "conditionally_eligible_for_bounded_live_smoke"
    assert not blockers
    assert any("4d2" in w for w in warnings)


def test_codex_profile_includes_implementer():
    profile = get_profile("codex")
    assert "implementer" in profile.adapter_roles
    assert profile.auth_argv == ("login", "status")
    shape = build_synthetic_headless_argv("codex")
    assert shape and shape[0] == "exec"
    assert build_synthetic_headless_argv("codex", include_prompt_text=True) is None


def test_codex_noninteractive_contract_dimensions():
    profile = get_profile("codex")
    help_text = (
        "Usage: codex exec [OPTIONS] [PROMPT]\n"
        "  --json\n  --ephemeral\n  --sandbox <MODE>\n  -C, --cd <DIR>\n"
    )
    assessment = assess_noninteractive_contract(
        profile,
        discovery_installed=True,
        help_text=help_text,
    )
    names = {d.name for d in assessment.dimensions}
    assert "ephemeral_session" in names
    assert "sandbox_control" in names
    assert "json_event_output" in names
    assert assessment.overall_status in (
        "supported_documented",
        "supported_verified",
    )


def test_jsonl_normalization_success_and_malformed():
    lines = [
        json.dumps({"type": "thread.started", "thread_id": "t1"}),
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "agent.message", "message": "hello world"}),
        json.dumps({"type": "usage", "input_tokens": 3, "output_tokens": 2}),
        json.dumps({"type": "turn.completed"}),
    ]
    result = normalize_codex_jsonl("\n".join(lines))
    assert result.provider_result_status == "success"
    assert result.raw_jsonl_persisted is False
    assert result.final_safe_message == "hello world"
    assert result.usage and result.usage.get("input_tokens") == 3

    bad = normalize_codex_jsonl("{not-json}\n" + json.dumps({"type": "turn.started"}))
    assert bad.malformed_event_count >= 1
    assert bad.incomplete_turn is True


def test_jsonl_auth_and_quota_errors():
    auth = normalize_codex_jsonl(
        json.dumps({"type": "error", "message": "authentication failed: please login"})
    )
    assert "authentication_failure_detected" in auth.notes
    quota = normalize_codex_jsonl(
        json.dumps({"type": "error", "message": "usage limit exceeded"})
    )
    assert "quota_or_usage_limit_detected" in quota.notes


def test_future_exec_argv_refuses_prompt():
    assert (
        build_future_codex_exec_argv(
            pinned_executable="codex",
            worktree_path="C:/wt",
            sandbox_mode="workspace-write",
            prompt_text="PING",
        )
        is None
    )
    argv = build_future_codex_exec_argv(
        pinned_executable="codex",
        worktree_path="C:/wt",
        sandbox_mode="workspace-write",
        prompt_text=None,
    )
    assert argv is not None
    assert "PING" not in argv
    assert "--json" in argv and "--ephemeral" in argv


def test_env_sanitization_strips_api_key():
    src = {
        "PATH": "C:\\Windows\\System32",
        "OPENAI_API_KEY": "sk-secret-should-not-leak",
        "CODEX_HOME": "C:\\Users\\x\\.codex",
        "HTTP_PROXY": "http://proxy.example",
        "TEMP": "C:\\Temp",
    }
    presence = report_codex_env_presence(src)
    assert presence.openai_api_key_present is True
    assert presence.codex_home_present is True
    assert "sk-secret" not in json.dumps(presence.to_dict())
    child = build_codex_child_environment(src, authentication_mode="chatgpt")
    assert "OPENAI_API_KEY" not in child
    assert "CODEX_HOME" not in child
    assert child.get("PATH")


def test_fresh_context_not_independent():
    independence, combos = compute_independence(
        [
            {
                "provider_id": "codex",
                "implementer_eligibility": "eligible",
                "reviewer_eligibility": "eligible",
                "final_readiness_verdict": "conditionally_eligible_for_bounded_live_smoke",
            }
        ]
    )
    assert independence == "fresh_context_same_provider_only"
    assert combos and combos[0].category == "fresh_context_same_provider"


def test_round4d2_recommendation_envelope_shape():
    from ai_dev_os.providers.codex_round4d2_envelope import propose_round4d2_codex_envelope

    env = propose_round4d2_codex_envelope(
        pinned_executable_id="pin_test",
        executable_fingerprint_prefix="abcd1234",
        cli_version="codex-cli 0.0.0",
        authentication_mode="chatgpt",
    )
    assert env["provider_id"] == "codex"
    assert env["target_project"] == "calculator-demo"
    assert env["maximum_repair_rounds"] == 1
    assert env["live_execution_authorized"] is False
    assert env["requires_separate_explicit_authorization"] is True
    assert env["codex_exec_with_prompt_authorized"] is False
