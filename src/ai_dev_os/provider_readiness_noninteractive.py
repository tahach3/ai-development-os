"""Noninteractive execution contract assessment (Round 4D1.2) — never live prompts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .provider_readiness_constants import NONINTERACTIVE_CONTRACT_POLICY_VERSION
from .provider_readiness_models import CapabilityStatus, NoninteractiveStatus
from .provider_readiness_profiles import ProviderReadinessProfile

# Help phrases indicating a desktop/editor CLI (not a headless agent runner).
_EDITOR_CLI_HINTS = re.compile(
    r"(?i)("
    r"--diff\b|--goto\b|--new-window\b|--reuse-window\b|"
    r"--list-extensions\b|--install-extension\b|"
    r"Compare two files|Open a file at the path|Force to open a new window"
    r")"
)

# Help phrases that *document* headless / noninteractive agent-style execution.
# Detection only — these tokens must NEVER be executed by readiness probes.
_HEADLESS_DOC_HINTS = re.compile(
    r"(?i)("
    r"--print\b|headless|non[\s-]?interactive|stdin\b|"
    r"--output-format\b|--json\b|structured\s+output|"
    r"--working-directory\b|--cwd\b|--workdir\b|-C\b|--cd\b|"
    r"--timeout\b|--max-turns\b|"
    r"--ephemeral\b|--sandbox\b|\bexec\b"
    r")"
)

# Dangerous live-invocation markers in help (evidence only).
_LIVE_INVOKE_HINTS = re.compile(
    r"(?i)(\bagent\b|\bprompt\b|\bchat\b|--yes\b|\bauto[\s-]?approve\b)"
)


@dataclass
class ContractDimension:
    name: str
    status: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NoninteractiveContractAssessment:
    policy_version: str
    overall_status: str
    overall_evidence: str
    editor_cli_detected: bool
    headless_documented: bool
    synthetic_verified: bool
    dimensions: list[ContractDimension] = field(default_factory=list)
    would_be_argv_allowlisted: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": [d.to_dict() for d in self.dimensions],
            "editor_cli_detected": self.editor_cli_detected,
            "headless_documented": self.headless_documented,
            "notes": list(self.notes),
            "overall_evidence": self.overall_evidence,
            "overall_status": self.overall_status,
            "policy_version": self.policy_version,
            "synthetic_verified": self.synthetic_verified,
            "would_be_argv_allowlisted": self.would_be_argv_allowlisted,
        }


# Adapter-documented headless argv *shapes* for synthetic verification.
# These are documentation/allowlist shapes — readiness never appends prompt text.
DOCUMENTED_HEADLESS_ARGV_SHAPES: dict[str, tuple[str, ...]] = {
    "claude_code": ("--print", "--output-format", "json"),
    # Prompt text intentionally omitted from the documented shape.
    "codex": ("exec", "--json", "--ephemeral", "--sandbox", "-C"),
    # Cursor editor has no safe headless agent argv shape in adapter allowlists.
}


def _dim(name: str, status: str, evidence: str) -> ContractDimension:
    return ContractDimension(name=name, status=status, evidence=evidence)


def assess_noninteractive_contract(
    profile: ProviderReadinessProfile,
    *,
    discovery_installed: bool,
    help_text: str | None = None,
    synthetic_verified: bool = False,
    force_editor_cli: bool | None = None,
) -> NoninteractiveContractAssessment:
    """Assess noninteractive readiness from profile/help/synthetic fixtures only."""
    notes: list[str] = []
    help = help_text or ""
    editor = bool(force_editor_cli) if force_editor_cli is not None else bool(
        _EDITOR_CLI_HINTS.search(help)
    )
    if profile.requires_automation_cli_proof and discovery_installed and not help.strip():
        # Without help, Cursor-like providers stay ambiguous unless synthetic.
        editor = False

    headless_doc = bool(_HEADLESS_DOC_HINTS.search(help)) or profile.noninteractive_documented
    live_hints = bool(_LIVE_INVOKE_HINTS.search(help))
    if live_hints:
        notes.append("help_mentions_interactive_or_agent_tokens_as_data_only")

    # Dimension assessments (never from live prompts).
    if not discovery_installed and not profile.synthetic:
        dims = [
            _dim("prompt_input", CapabilityStatus.UNAVAILABLE.value, "not_installed"),
            _dim("working_directory_binding", CapabilityStatus.UNAVAILABLE.value, "not_installed"),
            _dim("structured_output", CapabilityStatus.UNAVAILABLE.value, "not_installed"),
            _dim("timeout", CapabilityStatus.UNAVAILABLE.value, "not_installed"),
            _dim("cancellation", CapabilityStatus.UNAVAILABLE.value, "not_installed"),
            _dim("output_limits", CapabilityStatus.UNAVAILABLE.value, "not_installed"),
        ]
        return NoninteractiveContractAssessment(
            policy_version=NONINTERACTIVE_CONTRACT_POLICY_VERSION,
            overall_status=NoninteractiveStatus.UNAVAILABLE.value,
            overall_evidence="not_installed",
            editor_cli_detected=False,
            headless_documented=False,
            synthetic_verified=False,
            dimensions=dims,
            notes=notes,
        )

    shape = DOCUMENTED_HEADLESS_ARGV_SHAPES.get(profile.provider_id)
    shape_ok = shape is not None and profile.noninteractive_documented

    if synthetic_verified or profile.synthetic_verified_noninteractive:
        prompt_st = CapabilityStatus.SUPPORTED_VERIFIED.value
        wd_st = CapabilityStatus.SUPPORTED_VERIFIED.value
        out_st = CapabilityStatus.SUPPORTED_VERIFIED.value
        overall = NoninteractiveStatus.SUPPORTED_VERIFIED.value
        evidence = "synthetic_fixture_contract"
        synth = True
    elif editor and profile.requires_automation_cli_proof:
        prompt_st = CapabilityStatus.UNSUPPORTED_VERIFIED.value
        wd_st = CapabilityStatus.AMBIGUOUS.value
        out_st = CapabilityStatus.UNSUPPORTED_VERIFIED.value
        overall = NoninteractiveStatus.UNSUPPORTED_VERIFIED.value
        evidence = "editor_cli_help_not_headless_agent"
        synth = False
        notes.append("cursor_or_editor_cli_insufficient_for_noninteractive_live_smoke")
    elif profile.requires_automation_cli_proof:
        prompt_st = CapabilityStatus.AMBIGUOUS.value
        wd_st = CapabilityStatus.AMBIGUOUS.value
        out_st = CapabilityStatus.AMBIGUOUS.value
        overall = NoninteractiveStatus.AMBIGUOUS.value
        evidence = "automation_cli_not_proven"
        synth = False
    elif headless_doc or shape_ok:
        prompt_st = CapabilityStatus.SUPPORTED_DOCUMENTED.value
        wd_st = CapabilityStatus.SUPPORTED_DOCUMENTED.value
        out_st = CapabilityStatus.SUPPORTED_DOCUMENTED.value
        overall = NoninteractiveStatus.SUPPORTED_DOCUMENTED.value
        evidence = "adapter_contract_and_or_help"
        synth = False
    elif discovery_installed:
        prompt_st = CapabilityStatus.AMBIGUOUS.value
        wd_st = CapabilityStatus.AMBIGUOUS.value
        out_st = CapabilityStatus.AMBIGUOUS.value
        overall = NoninteractiveStatus.AMBIGUOUS.value
        evidence = "installed_but_noninteractive_unproven"
        synth = False
    else:
        prompt_st = CapabilityStatus.UNAVAILABLE.value
        wd_st = CapabilityStatus.UNAVAILABLE.value
        out_st = CapabilityStatus.UNAVAILABLE.value
        overall = NoninteractiveStatus.UNAVAILABLE.value
        evidence = "not_assessed"
        synth = False

    # Timeout / cancel / output limits: always from OS/runner policy when installed.
    if discovery_installed or profile.synthetic or synth:
        timeout_st = CapabilityStatus.SUPPORTED_VERIFIED.value
        cancel_st = CapabilityStatus.SUPPORTED_DOCUMENTED.value
        limits_st = CapabilityStatus.SUPPORTED_VERIFIED.value
        timeout_ev = "runner_probe_timeout_policy"
        cancel_ev = "cancel_request_store_contract"
        limits_ev = "probe_output_truncation_policy"
    else:
        timeout_st = cancel_st = limits_st = CapabilityStatus.UNAVAILABLE.value
        timeout_ev = cancel_ev = limits_ev = "not_installed"

    dims = [
        _dim("prompt_input", prompt_st, "adapter_or_help" if not synth else "synthetic_fixture"),
        _dim("working_directory_binding", wd_st, "adapter_or_help" if not synth else "synthetic_fixture"),
        _dim("structured_output", out_st, "adapter_envelope" if not synth else "synthetic_fixture"),
        _dim("timeout", timeout_st, timeout_ev),
        _dim("cancellation", cancel_st, cancel_ev),
        _dim("output_limits", limits_st, limits_ev),
    ]

    # Codex-specific documented capabilities (help/adapter only; never live-proven here).
    if profile.provider_id == "codex" and (discovery_installed or synth or profile.synthetic):
        ephemeral_doc = bool(re.search(r"(?i)--ephemeral\b", help)) or shape_ok
        sandbox_doc = bool(re.search(r"(?i)--sandbox\b", help)) or shape_ok
        json_doc = bool(re.search(r"(?i)--json\b", help)) or shape_ok
        eph_st = (
            CapabilityStatus.SUPPORTED_VERIFIED.value
            if synth
            else (
                CapabilityStatus.SUPPORTED_DOCUMENTED.value
                if ephemeral_doc
                else CapabilityStatus.AMBIGUOUS.value
            )
        )
        sb_st = (
            CapabilityStatus.SUPPORTED_VERIFIED.value
            if synth
            else (
                CapabilityStatus.SUPPORTED_DOCUMENTED.value
                if sandbox_doc
                else CapabilityStatus.AMBIGUOUS.value
            )
        )
        js_st = (
            CapabilityStatus.SUPPORTED_VERIFIED.value
            if synth
            else (
                CapabilityStatus.SUPPORTED_DOCUMENTED.value
                if json_doc
                else CapabilityStatus.AMBIGUOUS.value
            )
        )
        dims.extend(
            [
                _dim("ephemeral_session", eph_st, "codex_help_or_adapter"),
                _dim("sandbox_control", sb_st, "codex_help_or_adapter"),
                _dim("json_event_output", js_st, "codex_help_or_adapter"),
            ]
        )
        notes.append("codex_exec_prompt_never_invoked_during_readiness")

    return NoninteractiveContractAssessment(
        policy_version=NONINTERACTIVE_CONTRACT_POLICY_VERSION,
        overall_status=overall,
        overall_evidence=evidence,
        editor_cli_detected=editor,
        headless_documented=bool(headless_doc),
        synthetic_verified=synth,
        dimensions=dims,
        would_be_argv_allowlisted=bool(shape_ok or synth),
        notes=notes,
    )


def build_synthetic_headless_argv(
    provider_id: str,
    *,
    include_prompt_text: bool = False,
) -> tuple[str, ...] | None:
    """Return documented headless argv shape for synthetic checks.

    If ``include_prompt_text`` is True, returns None (refused) — readiness must never
    construct live prompt argv.
    """
    if include_prompt_text:
        return None
    return DOCUMENTED_HEADLESS_ARGV_SHAPES.get(provider_id)
