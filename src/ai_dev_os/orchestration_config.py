"""Versioned Round 3C orchestration configuration — fail-closed defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .orchestration_models import (
    ORCHESTRATION_CONFIG_SCHEMA_VERSION,
    ORCHESTRATION_POLICY_VERSION,
    OrchestrationState,
)
from .repair_rounds import load_max_repair_rounds


class OrchestrationConfigError(ValueError):
    """Raised when orchestration configuration is missing or unsafe."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_orchestration_config_path() -> Path:
    return _repo_root() / "config" / "orchestration.yaml"


@dataclass
class OrchestrationConfig:
    schema_version: str = ORCHESTRATION_CONFIG_SCHEMA_VERSION
    policy_version: str = ORCHESTRATION_POLICY_VERSION
    default_provider_id: str = "simulated"
    default_invocation_mode: str = "simulated"
    allow_live_providers: bool = False
    implementation_role: str = "cursor"
    review_role: str = "codex"
    implementation_provider_id: str = "simulated"
    review_provider_id: str = "simulated"
    max_repair_rounds: int = 3
    max_total_steps: int = 40
    consecutive_no_progress_threshold: int = 2
    oscillation_history_window: int = 6
    default_timeout_seconds: float = 30.0
    default_output_limit_bytes: int = 65536
    allow_pass_with_notes_completion: bool = True
    allow_test_failure_repair: bool = True
    stalemate_state: str = OrchestrationState.HUMAN_REVIEW_REQUIRED.value
    repair_limit_state: str = OrchestrationState.BLOCKED.value
    step_limit_state: str = OrchestrationState.BLOCKED.value
    human_review_on_stalemate: bool = True
    human_review_on_repair_limit: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_live_providers": self.allow_live_providers,
            "allow_pass_with_notes_completion": self.allow_pass_with_notes_completion,
            "allow_test_failure_repair": self.allow_test_failure_repair,
            "consecutive_no_progress_threshold": self.consecutive_no_progress_threshold,
            "default_invocation_mode": self.default_invocation_mode,
            "default_output_limit_bytes": self.default_output_limit_bytes,
            "default_provider_id": self.default_provider_id,
            "default_timeout_seconds": self.default_timeout_seconds,
            "human_review_on_repair_limit": self.human_review_on_repair_limit,
            "human_review_on_stalemate": self.human_review_on_stalemate,
            "implementation_provider_id": self.implementation_provider_id,
            "implementation_role": self.implementation_role,
            "max_repair_rounds": self.max_repair_rounds,
            "max_total_steps": self.max_total_steps,
            "oscillation_history_window": self.oscillation_history_window,
            "policy_version": self.policy_version,
            "repair_limit_state": self.repair_limit_state,
            "review_provider_id": self.review_provider_id,
            "review_role": self.review_role,
            "schema_version": self.schema_version,
            "stalemate_state": self.stalemate_state,
            "step_limit_state": self.step_limit_state,
        }


def fail_closed_default_orchestration_config() -> OrchestrationConfig:
    return OrchestrationConfig()


def _require_positive(name: str, value: int) -> int:
    if not isinstance(value, int) or value < 1:
        raise OrchestrationConfigError(f"{name} must be a positive integer (got {value!r})")
    return value


def validate_orchestration_config(cfg: OrchestrationConfig) -> OrchestrationConfig:
    if cfg.schema_version != ORCHESTRATION_CONFIG_SCHEMA_VERSION:
        raise OrchestrationConfigError(
            f"Unsupported orchestration config schema: {cfg.schema_version}"
        )
    if cfg.policy_version != ORCHESTRATION_POLICY_VERSION:
        raise OrchestrationConfigError(
            f"Unsupported orchestration policy version: {cfg.policy_version}"
        )
    if cfg.default_invocation_mode != "simulated" and not cfg.allow_live_providers:
        raise OrchestrationConfigError(
            "Incompatible provider mode: non-simulated requires allow_live_providers"
        )
    if cfg.allow_live_providers:
        raise OrchestrationConfigError(
            "Round 3C refuses allow_live_providers=true (fail closed)"
        )
    if cfg.default_invocation_mode != "simulated":
        raise OrchestrationConfigError("Round 3C requires default_invocation_mode=simulated")
    for pid in (
        cfg.default_provider_id,
        cfg.implementation_provider_id,
        cfg.review_provider_id,
    ):
        if pid != "simulated":
            raise OrchestrationConfigError(
                f"Round 3C requires simulated providers (got {pid!r})"
            )
    cfg.max_repair_rounds = _require_positive("max_repair_rounds", cfg.max_repair_rounds)
    cfg.max_total_steps = _require_positive("max_total_steps", cfg.max_total_steps)
    cfg.consecutive_no_progress_threshold = _require_positive(
        "consecutive_no_progress_threshold", cfg.consecutive_no_progress_threshold
    )
    cfg.oscillation_history_window = _require_positive(
        "oscillation_history_window", cfg.oscillation_history_window
    )
    if cfg.default_timeout_seconds <= 0:
        raise OrchestrationConfigError("default_timeout_seconds must be > 0")
    if cfg.default_output_limit_bytes < 1:
        raise OrchestrationConfigError("default_output_limit_bytes must be >= 1")
    global_ceiling = load_max_repair_rounds()
    if cfg.max_repair_rounds > global_ceiling:
        raise OrchestrationConfigError(
            f"max_repair_rounds {cfg.max_repair_rounds} exceeds global ceiling {global_ceiling}"
        )
    for name, state in (
        ("stalemate_state", cfg.stalemate_state),
        ("repair_limit_state", cfg.repair_limit_state),
        ("step_limit_state", cfg.step_limit_state),
    ):
        try:
            OrchestrationState(state)
        except ValueError as exc:
            raise OrchestrationConfigError(f"Invalid {name}: {state}") from exc
    return cfg


def load_orchestration_config(path: Path | None = None) -> OrchestrationConfig:
    cfg_path = path or default_orchestration_config_path()
    if not cfg_path.exists():
        raise OrchestrationConfigError(f"Missing orchestration config: {cfg_path}")
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise OrchestrationConfigError("Malformed orchestration config: expected mapping")
    try:
        cfg = OrchestrationConfig(
            schema_version=str(data.get("schema_version") or ""),
            policy_version=str(data.get("policy_version") or ""),
            default_provider_id=str(data.get("default_provider_id") or "simulated"),
            default_invocation_mode=str(data.get("default_invocation_mode") or "simulated"),
            allow_live_providers=bool(data.get("allow_live_providers", False)),
            implementation_role=str(data.get("implementation_role") or "cursor"),
            review_role=str(data.get("review_role") or "codex"),
            implementation_provider_id=str(
                data.get("implementation_provider_id") or "simulated"
            ),
            review_provider_id=str(data.get("review_provider_id") or "simulated"),
            max_repair_rounds=int(data.get("max_repair_rounds", 3)),
            max_total_steps=int(data.get("max_total_steps", 40)),
            consecutive_no_progress_threshold=int(
                data.get("consecutive_no_progress_threshold", 2)
            ),
            oscillation_history_window=int(data.get("oscillation_history_window", 6)),
            default_timeout_seconds=float(data.get("default_timeout_seconds", 30)),
            default_output_limit_bytes=int(data.get("default_output_limit_bytes", 65536)),
            allow_pass_with_notes_completion=bool(
                data.get("allow_pass_with_notes_completion", True)
            ),
            allow_test_failure_repair=bool(data.get("allow_test_failure_repair", True)),
            stalemate_state=str(
                data.get("stalemate_state")
                or OrchestrationState.HUMAN_REVIEW_REQUIRED.value
            ),
            repair_limit_state=str(
                data.get("repair_limit_state") or OrchestrationState.BLOCKED.value
            ),
            step_limit_state=str(
                data.get("step_limit_state") or OrchestrationState.BLOCKED.value
            ),
            human_review_on_stalemate=bool(data.get("human_review_on_stalemate", True)),
            human_review_on_repair_limit=bool(data.get("human_review_on_repair_limit", True)),
        )
    except (TypeError, ValueError) as exc:
        raise OrchestrationConfigError(f"Malformed orchestration config: {exc}") from exc
    return validate_orchestration_config(cfg)
