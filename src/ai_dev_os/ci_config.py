"""Load and validate Round 4A CI policy configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .ci_models import CI_POLICY_VERSION, CI_SCHEMA_VERSION, STAGE_ORDER


class CIConfigError(ValueError):
    """Raised when CI policy is missing, malformed, or unsupported."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_ci_policy_path() -> Path:
    return _repo_root() / "config" / "ci_policy.yaml"


@dataclass
class CIPolicy:
    schema_version: str = CI_SCHEMA_VERSION
    policy_version: str = CI_POLICY_VERSION
    requires_python: str = ">=3.11"
    python_versions: list[str] = field(default_factory=lambda: ["3.11"])
    default_timeout_seconds: float = 60.0
    compile_timeout_seconds: float = 120.0
    pytest_timeout_seconds: float = 600.0
    max_timeout_seconds: float = 900.0
    output_limit_bytes: int = 65_536
    require_clean_worktree: bool = False
    persist_results: bool = False
    results_dirname: str = "ci_runs"
    stages: list[str] = field(default_factory=lambda: list(STAGE_ORDER))
    prohibited_dependency_names: list[str] = field(default_factory=list)
    prohibited_path_substrings: list[str] = field(default_factory=list)
    runtime_artifact_globs: list[str] = field(default_factory=list)
    safety_critical_path_prefixes: list[str] = field(default_factory=list)

    def clamp_timeout(self, value: float | None, *, default: float) -> float:
        timeout = float(default if value is None else value)
        if timeout <= 0:
            raise CIConfigError("Timeout must be positive")
        return min(timeout, self.max_timeout_seconds)


def validate_ci_policy(raw: dict[str, Any]) -> CIPolicy:
    if not isinstance(raw, dict):
        raise CIConfigError("CI policy must be a mapping")
    schema_version = str(raw.get("schema_version", ""))
    policy_version = str(raw.get("policy_version", ""))
    if schema_version != CI_SCHEMA_VERSION:
        raise CIConfigError(f"Unsupported CI schema version: {schema_version!r}")
    if policy_version != CI_POLICY_VERSION:
        raise CIConfigError(f"Unsupported CI policy version: {policy_version!r}")

    stages = list(raw.get("stages") or list(STAGE_ORDER))
    if stages != list(STAGE_ORDER):
        # Allow exact STAGE_ORDER only — fail closed on reorder/omit/extra.
        if set(stages) != set(STAGE_ORDER) or len(stages) != len(STAGE_ORDER):
            raise CIConfigError("CI stages must match the fixed STAGE_ORDER set")
        # Reorder attempt: normalize to STAGE_ORDER but record as error for safety.
        if stages != list(STAGE_ORDER):
            raise CIConfigError("CI stage order must match fixed STAGE_ORDER exactly")

    return CIPolicy(
        schema_version=schema_version,
        policy_version=policy_version,
        requires_python=str(raw.get("requires_python", ">=3.11")),
        python_versions=[str(v) for v in (raw.get("python_versions") or ["3.11"])],
        default_timeout_seconds=float(raw.get("default_timeout_seconds", 60)),
        compile_timeout_seconds=float(raw.get("compile_timeout_seconds", 120)),
        pytest_timeout_seconds=float(raw.get("pytest_timeout_seconds", 600)),
        max_timeout_seconds=float(raw.get("max_timeout_seconds", 900)),
        output_limit_bytes=int(raw.get("output_limit_bytes", 65_536)),
        require_clean_worktree=bool(raw.get("require_clean_worktree", False)),
        persist_results=bool(raw.get("persist_results", False)),
        results_dirname=str(raw.get("results_dirname", "ci_runs")),
        stages=list(STAGE_ORDER),
        prohibited_dependency_names=[
            str(x).lower() for x in (raw.get("prohibited_dependency_names") or [])
        ],
        prohibited_path_substrings=[
            str(x).lower() for x in (raw.get("prohibited_path_substrings") or [])
        ],
        runtime_artifact_globs=[str(x) for x in (raw.get("runtime_artifact_globs") or [])],
        safety_critical_path_prefixes=[
            str(x).replace("\\", "/") for x in (raw.get("safety_critical_path_prefixes") or [])
        ],
    )


def load_ci_policy(path: Path | None = None) -> CIPolicy:
    policy_path = path or default_ci_policy_path()
    if not policy_path.exists():
        raise CIConfigError(f"CI policy not found: {policy_path}")
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CIConfigError(f"Malformed CI policy YAML: {exc}") from exc
    return validate_ci_policy(raw)


def fail_closed_default_ci_policy() -> CIPolicy:
    """In-memory default matching STAGE_ORDER when file unavailable in tests."""
    return CIPolicy()
