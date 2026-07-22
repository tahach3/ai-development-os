"""Staleness detection for provider readiness records (Round 4D1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .provider_readiness_constants import (
    AUTHENTICATION_PROBE_POLICY_VERSION,
    EXECUTABLE_TRUST_POLICY_VERSION,
    READINESS_POLICY_VERSION,
    READINESS_SCHEMA_VERSION,
    ROLE_ELIGIBILITY_POLICY_VERSION,
    SAFE_RUNNER_POLICY_VERSION,
    VERSION_COMPATIBILITY_POLICY_VERSION,
)
from .provider_readiness_models import ProviderReadinessRecord, ReadinessFailureClass


@dataclass
class StalenessResult:
    stale: bool
    reasons: list[str]
    failure_class: str = ReadinessFailureClass.NONE.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class,
            "reasons": list(self.reasons),
            "stale": self.stale,
        }


def evaluate_staleness(
    record: ProviderReadinessRecord | dict[str, Any],
    *,
    repository_commit: str,
    adapter_version: str,
    executable_fingerprint: str | None,
    executable_path_sanitized: str | None = None,
    cli_version: str | None = None,
    provider_config_fingerprint: str | None = None,
    project_registration_fingerprint: str | None = None,
) -> StalenessResult:
    data = record.to_dict() if isinstance(record, ProviderReadinessRecord) else dict(record)
    reasons: list[str] = []

    if data.get("schema_version") != READINESS_SCHEMA_VERSION:
        reasons.append("schema_version_changed")
    if data.get("readiness_policy_version") != READINESS_POLICY_VERSION:
        reasons.append("readiness_policy_version_changed")
    if data.get("executable_trust_policy_version") != EXECUTABLE_TRUST_POLICY_VERSION:
        reasons.append("executable_trust_policy_version_changed")
    if data.get("version_compatibility_policy_version") != VERSION_COMPATIBILITY_POLICY_VERSION:
        reasons.append("version_compatibility_policy_version_changed")
    if data.get("authentication_probe_policy_version") != AUTHENTICATION_PROBE_POLICY_VERSION:
        reasons.append("authentication_probe_policy_version_changed")
    if data.get("role_eligibility_policy_version") != ROLE_ELIGIBILITY_POLICY_VERSION:
        reasons.append("role_eligibility_policy_version_changed")
    if data.get("safe_runner_policy_version") != SAFE_RUNNER_POLICY_VERSION:
        reasons.append("safe_runner_policy_version_changed")
    if data.get("repository_commit") != repository_commit:
        reasons.append("repository_commit_changed")
    if data.get("adapter_version") != adapter_version:
        reasons.append("adapter_version_changed")
    if executable_fingerprint is not None and data.get("executable_fingerprint") != executable_fingerprint:
        reasons.append("executable_fingerprint_changed")
    if (
        executable_path_sanitized is not None
        and data.get("sanitized_executable_location") != executable_path_sanitized
    ):
        reasons.append("executable_path_changed")
    if cli_version is not None and data.get("cli_version") != cli_version:
        reasons.append("cli_version_changed")

    src = data.get("source_fingerprints") or {}
    if provider_config_fingerprint is not None:
        if src.get("provider_config") != provider_config_fingerprint:
            reasons.append("provider_config_changed")
    if project_registration_fingerprint is not None:
        if src.get("project_registration") != project_registration_fingerprint:
            reasons.append("project_registration_changed")

    stale = bool(reasons)
    return StalenessResult(
        stale=stale,
        reasons=reasons,
        failure_class=ReadinessFailureClass.STALE_RECORD.value if stale else ReadinessFailureClass.NONE.value,
    )


def validate_record_structure(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "readiness_id",
        "schema_version",
        "readiness_policy_version",
        "provider_id",
        "final_readiness_verdict",
        "live_provider_invocations",
        "record_fingerprint",
    ]
    for key in required:
        if key not in data:
            errors.append(f"missing_field:{key}")
    if data.get("live_provider_invocations") not in (0, "0"):
        errors.append("live_provider_invocations_must_be_zero")
    if data.get("schema_version") and data.get("schema_version") != READINESS_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")
    return errors
