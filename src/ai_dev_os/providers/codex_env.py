"""Codex environment sanitization policy (Round 4D1.3)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Mapping

from ..provider_readiness_constants import CODEX_ENV_SANITIZATION_POLICY_VERSION
from ..safe_policy import ALLOWED_ENV_KEYS, SECRET_ENV_RE, filter_environment

# Observed for presence booleans only — values are never copied into reports.
CODEX_SENSITIVE_PRESENCE_KEYS = (
    "OPENAI_API_KEY",
    "CODEX_HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)

# Never inherit into Codex child env for ChatGPT-authenticated runs.
CODEX_BLOCKED_INHERIT_KEYS = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENAI_API_KEY_ID",
        "ANTHROPIC_API_KEY",
        "CURSOR_API_KEY",
    }
)


@dataclass(frozen=True)
class CodexEnvPresenceReport:
    policy_version: str
    openai_api_key_present: bool
    codex_home_present: bool
    http_proxy_present: bool
    https_proxy_present: bool
    all_proxy_present: bool
    no_proxy_present: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def report_codex_env_presence(
    source: Mapping[str, str] | None = None,
) -> CodexEnvPresenceReport:
    env = source if source is not None else os.environ
    return CodexEnvPresenceReport(
        policy_version=CODEX_ENV_SANITIZATION_POLICY_VERSION,
        openai_api_key_present=bool(env.get("OPENAI_API_KEY")),
        codex_home_present=bool(env.get("CODEX_HOME")),
        http_proxy_present=bool(env.get("HTTP_PROXY") or env.get("http_proxy")),
        https_proxy_present=bool(env.get("HTTPS_PROXY") or env.get("https_proxy")),
        all_proxy_present=bool(env.get("ALL_PROXY") or env.get("all_proxy")),
        no_proxy_present=bool(env.get("NO_PROXY") or env.get("no_proxy")),
        notes=(
            "values_not_printed",
            "chatgpt_mode_does_not_require_api_key_in_child_env",
            "credentials_not_copied_into_worktrees",
        ),
    )


def build_codex_child_environment(
    source: Mapping[str, str] | None = None,
    *,
    authentication_mode: str = "chatgpt",
) -> dict[str, str]:
    """Build sanitized child env for a future Codex invocation.

    ChatGPT mode: do not copy API keys. Never copy CODEX_HOME by inventing a
    workspace copy of credentials. Uses the same base allowlist as safe_exec.
    """
    base = filter_environment(dict(source) if source is not None else None)
    # filter_environment already drops secret-like keys; defend in depth.
    for key in list(base.keys()):
        if key in CODEX_BLOCKED_INHERIT_KEYS or SECRET_ENV_RE.search(key):
            base.pop(key, None)
        if key not in ALLOWED_ENV_KEYS:
            base.pop(key, None)
    if authentication_mode == "chatgpt":
        base.pop("OPENAI_API_KEY", None)
    # Do not inject or relocate CODEX_HOME into repository workspaces.
    return base
