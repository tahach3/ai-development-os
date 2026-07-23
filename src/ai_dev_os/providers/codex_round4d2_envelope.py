"""Proposed Round 4D2 Codex configuration envelope (never executes)."""

from __future__ import annotations

from typing import Any

from ..provider_models import PROVIDER_ADAPTER_VERSION
from ..provider_readiness_constants import (
    AUTHENTICATION_MODE_POLICY_VERSION,
    CODEX_COMPATIBILITY_POLICY_VERSION,
    CODEX_ENV_SANITIZATION_POLICY_VERSION,
    CODEX_EVENT_NORMALIZATION_SCHEMA_VERSION,
    NONINTERACTIVE_CONTRACT_POLICY_VERSION,
    READINESS_POLICY_VERSION,
)


def propose_round4d2_codex_envelope(
    *,
    pinned_executable_id: str,
    executable_fingerprint_prefix: str,
    cli_version: str,
    authentication_mode: str = "chatgpt",
    repository_commit: str | None = None,
) -> dict[str, Any]:
    """Exact proposed Round 4D2 config — documentation/tests only; does not run Codex."""
    return {
        "provider_id": "codex",
        "adapter_id": "codex",
        "adapter_version": PROVIDER_ADAPTER_VERSION,
        "pinned_executable_id": pinned_executable_id,
        "executable_fingerprint_prefix": executable_fingerprint_prefix[:16],
        "cli_version": cli_version,
        "authentication_mode": authentication_mode,
        "authentication_mode_policy_version": AUTHENTICATION_MODE_POLICY_VERSION,
        "target_project": "calculator-demo",
        "isolated_worktree_required": True,
        "starting_commit_binding_required": True,
        "starting_commit": repository_commit,
        "task_and_approved_plan_required": True,
        "sandbox_mode": "workspace-write",
        "network_policy": "provider_backend_only_documented",
        "timeout_seconds": 120,
        "maximum_output_size_bytes": 65536,
        "json_mode": True,
        "ephemeral_mode": True,
        "maximum_implementation_attempts": 1,
        "maximum_repair_rounds": 1,
        "reviewer_mode": "deterministic_non_model_validation_preferred",
        "reviewer_independence_limitation": (
            "fresh_context_same_provider_only_if_model_review_used;"
            "not_separate_provider_independence"
        ),
        "tests_to_run": ["targeted allowlisted pytest under approved worktree"],
        "stop_conditions": [
            "policy_block",
            "auth_failure",
            "timeout",
            "repair_limit",
            "stalemate",
            "operator_cancel",
        ],
        "usage_and_latency_evidence_required": True,
        "report_audience": "operator",
        "report_detail_level": "standard",
        "readiness_policy_version": READINESS_POLICY_VERSION,
        "noninteractive_contract_policy_version": NONINTERACTIVE_CONTRACT_POLICY_VERSION,
        "codex_event_normalization_schema": CODEX_EVENT_NORMALIZATION_SCHEMA_VERSION,
        "codex_env_sanitization_policy": CODEX_ENV_SANITIZATION_POLICY_VERSION,
        "codex_compatibility_policy": CODEX_COMPATIBILITY_POLICY_VERSION,
        "live_execution_authorized": False,
        "requires_separate_explicit_authorization": True,
        "codex_exec_with_prompt_authorized": False,
        "round_4d2_gate": "locked",
        "forbidden": [
            "danger-full-access",
            "dangerously-bypass-approvals-and-sandbox",
            "yolo",
            "unrestricted_network",
            "automatic_push_merge_deploy",
            "api_key_authentication_mode",
        ],
    }
