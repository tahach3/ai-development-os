"""Deterministic simulated provider — exercises real policy/audit/normalize paths."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..execution_audit import ExecutionAuditStore
from ..fingerprints import fingerprint
from ..models import utc_now_iso
from ..provider_audit import ProviderAuditStore
from ..provider_config import ProviderConfig
from ..provider_models import (
    AUTOMATION_SIMULATED,
    FailureClass,
    InstallationStatus,
    AvailabilityStatus,
    AuthCategory,
    NetworkUse,
    PROVIDER_ADAPTER_VERSION,
    PROVIDER_RESULT_SCHEMA_VERSION,
    PolicyDecision,
    ProviderCapability,
    ProviderId,
    ProviderMode,
    ProviderRequest,
    ProviderResultEnvelope,
    ProviderResultStatus,
    SimulatedFixture,
    rejected_provider_result,
)
from ..safe_exec import run_allowlisted
from ..safe_policy import DEFAULT_OUTPUT_LIMIT_BYTES, build_pytest_argv
from .base import ProviderAdapter


FIXTURE_PAYLOADS: dict[str, dict[str, Any]] = {
    SimulatedFixture.SUCCESS_IMPL.value: {
        "kind": "implementation",
        "summary": "Simulated implementation completed for calculator-demo.",
        "outcome": "success",
        "files_changed": ["calculator/ops.py"],
        "tests_run": ["tests/test_ops.py"],
    },
    SimulatedFixture.SUCCESS_REVIEW.value: {
        "kind": "review",
        "verdict": "pass",
        "summary": "Simulated independent review passed.",
        "findings": [],
    },
    SimulatedFixture.SUCCESS_REVIEW_WITH_NOTES.value: {
        "kind": "review",
        "verdict": "pass_with_notes",
        "summary": "Simulated review passed with notes.",
        "findings": [
            {
                "finding_id": "note-1",
                "severity": "note",
                "summary": "Minor style note",
                "path": "calculator/ops.py",
                "code": "STYLE",
            }
        ],
    },
    SimulatedFixture.CHANGES_REQUIRED_REVIEW.value: {
        "kind": "review",
        "verdict": "changes_required",
        "summary": "Simulated review requires changes.",
        "findings": [
            {
                "finding_id": "def-subtract",
                "severity": "major",
                "summary": "subtract implementation incorrect",
                "path": "calculator/ops.py",
                "code": "LOGIC",
            }
        ],
    },
    SimulatedFixture.CHANGES_REQUIRED_IDENTICAL.value: {
        "kind": "review",
        "verdict": "changes_required",
        "summary": "Simulated review requires identical changes.",
        "findings": [
            {
                "finding_id": "def-subtract",
                "severity": "major",
                "summary": "subtract implementation incorrect",
                "path": "calculator/ops.py",
                "code": "LOGIC",
            }
        ],
    },
    SimulatedFixture.MALFORMED_REVIEW.value: {
        "kind": "malformed",
        "not_a_valid_envelope": True,
    },
    SimulatedFixture.PROVIDER_REJECTION.value: {
        "kind": "rejection",
        "reason": "simulated provider rejected the request",
    },
    SimulatedFixture.MALFORMED_OUTPUT.value: {
        "kind": "malformed",
        "not_a_valid_envelope": True,
    },
    SimulatedFixture.TIMEOUT.value: {"kind": "timeout"},
    SimulatedFixture.NONZERO_EXIT.value: {"kind": "nonzero", "exit_code": 7},
    SimulatedFixture.TRUNCATED_OUTPUT.value: {
        "kind": "implementation",
        "summary": "x" * 2000,
        "outcome": "success",
        "files_changed": [],
        "tests_run": [],
    },
    SimulatedFixture.MISSING_ARTIFACT.value: {"kind": "missing_artifact"},
    SimulatedFixture.DUPLICATE_REQUEST.value: {"kind": "duplicate"},
    SimulatedFixture.STALE_PLAN.value: {"kind": "stale_plan"},
    SimulatedFixture.STALE_COMMIT.value: {"kind": "stale_commit"},
    SimulatedFixture.STALE_CONTEXT.value: {"kind": "stale_context"},
    SimulatedFixture.CANCELLED.value: {"kind": "cancelled"},
    SimulatedFixture.SCOPE_CHANGE.value: {
        "kind": "implementation",
        "summary": "Simulated scope-change attempt",
        "outcome": "success",
        "files_changed": ["calculator/ops.py", "UNPLANNED.md"],
        "tests_run": [],
        "scope_change": True,
        "reapproval_required": True,
    },
}


class SimulatedProviderAdapter(ProviderAdapter):
    provider_id = ProviderId.SIMULATED.value
    adapter_version = PROVIDER_ADAPTER_VERSION

    def describe_capabilities(
        self,
        *,
        config: ProviderConfig,
        discovery: dict[str, Any] | None = None,
    ) -> ProviderCapability:
        mode = config.effective_mode(self.provider_id)
        live = False
        return ProviderCapability(
            provider_id=self.provider_id,
            adapter_version=self.adapter_version,
            executable_identity="simulated",
            detected_version="simulated-3b.1",
            installation_status=InstallationStatus.NOT_APPLICABLE,
            availability_status=(
                AvailabilityStatus.SIMULATION_READY
                if mode is ProviderMode.SIMULATED
                else AvailabilityStatus.DISABLED
            ),
            supported_roles=["claude", "cursor", "codex"],
            supported_modes=[
                ProviderMode.DISABLED.value,
                ProviderMode.SIMULATED.value,
                ProviderMode.MANUAL_HANDOFF.value,
            ],
            supports_noninteractive=True,
            supports_stdin_prompt=False,
            supports_file_prompt=True,
            auth_category=AuthCategory.NOT_APPLICABLE,
            network_use=NetworkUse.NONE_EXPECTED,
            live_execution_permission=live,
            automation_status=AUTOMATION_SIMULATED
            if mode is ProviderMode.SIMULATED
            else "disabled",
            notes="Deterministic fixtures only; no live model calls.",
        )

    def preview_invocation(self, request: ProviderRequest) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "mode": request.invocation_mode.value,
            "executable_identity": "simulated",
            "sanitized_argument_array": [
                "simulated",
                "--fixture",
                request.fixture_id or SimulatedFixture.SUCCESS_IMPL.value,
                "--request-id",
                request.request_id,
            ],
            "live_model_call": False,
            "request_fingerprint": request.request_fingerprint(),
        }

    def execute(
        self,
        request: ProviderRequest,
        *,
        config: ProviderConfig,
        audit_store: ProviderAuditStore,
        confinement_root: str | None = None,
        workspace_root: Path | None = None,
        run_safe_pytest: bool = True,
    ) -> ProviderResultEnvelope:
        preview = self.preview_invocation(request)
        argv = list(preview["sanitized_argument_array"])
        fixture_id = request.fixture_id or SimulatedFixture.SUCCESS_IMPL.value

        # Duplicate detection via audit store
        prior = audit_store.find_by_fingerprint(request.request_fingerprint())
        if prior is not None and prior.request_id != request.request_id:
            if prior.provider_result_status in (
                ProviderResultStatus.SUCCESS,
                ProviderResultStatus.TIMEOUT,
                ProviderResultStatus.FAILED,
            ):
                dup = rejected_provider_result(
                    request,
                    reason="Duplicate provider request fingerprint",
                    failure_class=FailureClass.DUPLICATE_REQUEST,
                    status=ProviderResultStatus.DUPLICATE,
                    duplicate=True,
                    automation_status=AUTOMATION_SIMULATED,
                    executable_identity="simulated",
                    argv=argv,
                )
                audit_store.save_result(dup)
                return dup

        if fixture_id == SimulatedFixture.DUPLICATE_REQUEST.value:
            # Force duplicate path even on first id by saving a ghost prior fingerprint match
            ghost = rejected_provider_result(
                request,
                reason="seed",
                failure_class=FailureClass.NONE,
                status=ProviderResultStatus.SUCCESS,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            ghost.policy_decision = PolicyDecision.ALLOW
            ghost.failure_class = FailureClass.NONE
            ghost.request_id = f"prior-{request.request_id}"
            audit_store.save_result(ghost)
            dup = rejected_provider_result(
                request,
                reason="Duplicate provider request fingerprint",
                failure_class=FailureClass.DUPLICATE_REQUEST,
                status=ProviderResultStatus.DUPLICATE,
                duplicate=True,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            audit_store.save_result(dup)
            return dup

        if fixture_id == SimulatedFixture.STALE_PLAN.value:
            env = rejected_provider_result(
                request,
                reason="Stale plan fingerprint binding",
                failure_class=FailureClass.STALE_BINDING,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            audit_store.save_result(env)
            return env

        if fixture_id == SimulatedFixture.STALE_COMMIT.value:
            env = rejected_provider_result(
                request,
                reason="Stale starting commit binding",
                failure_class=FailureClass.STALE_BINDING,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            audit_store.save_result(env)
            return env

        if fixture_id == SimulatedFixture.STALE_CONTEXT.value:
            env = rejected_provider_result(
                request,
                reason="Stale context fingerprint binding",
                failure_class=FailureClass.STALE_BINDING,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            audit_store.save_result(env)
            return env

        if fixture_id == SimulatedFixture.CANCELLED.value or audit_store.is_cancel_requested(
            request.request_id
        ):
            env = rejected_provider_result(
                request,
                reason="Provider execution cancelled",
                failure_class=FailureClass.CANCELLED,
                status=ProviderResultStatus.CANCELLED,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            audit_store.save_result(env)
            return env

        started = time.perf_counter()
        started_at = utc_now_iso()

        # Exercise Round 3A safe runner + audit path when confinement is available.
        safe_exec_id = None
        if run_safe_pytest and confinement_root:
            tests_dir = Path(confinement_root) / "tests"
            if tests_dir.is_dir():
                try:
                    pytest_argv = build_pytest_argv(test_paths=["tests"], extra_flags=["-q"])
                    safe_env = run_allowlisted(
                        pytest_argv,
                        working_directory=confinement_root,
                        confinement_root=confinement_root,
                        timeout=min(request.timeout_seconds, 60.0),
                        output_limit_bytes=min(
                            request.output_limit_bytes, DEFAULT_OUTPUT_LIMIT_BYTES
                        ),
                        session_id=request.session_id,
                        task_id=request.task_id,
                        project_id=request.project_id,
                        starting_commit=request.starting_commit,
                        tests_requested=["tests"],
                        tests_executed=["tests"],
                    )
                    if workspace_root is not None:
                        store = ExecutionAuditStore(workspace_root=workspace_root)
                        store.save(safe_env)
                        safe_exec_id = safe_env.execution_id
                except Exception:
                    safe_exec_id = None

        if fixture_id == SimulatedFixture.TIMEOUT.value:
            env = ProviderResultEnvelope(
                schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
                request_id=request.request_id,
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                provider_cli_version="simulated-3b.1",
                task_id=request.task_id,
                plan_id=request.plan_id,
                project_id=request.project_id,
                session_id=request.session_id,
                worktree_id=request.worktree_id,
                role=request.role,
                invocation_mode=request.invocation_mode.value,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                sanitized_argument_array=argv,
                request_fingerprint=request.request_fingerprint(),
                context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
                approved_plan_fingerprint=request.approved_plan_fingerprint,
                starting_commit=request.starting_commit,
                started_at=started_at,
                finished_at=utc_now_iso(),
                duration_seconds=round(time.perf_counter() - started, 6),
                exit_code=None,
                timeout_status=True,
                cancellation_status=False,
                stdout_truncated=False,
                stderr_truncated=False,
                provider_result_status=ProviderResultStatus.TIMEOUT,
                failure_class=FailureClass.TIMEOUT,
                result_artifact_path=None,
                result_fingerprint=None,
                policy_decision=PolicyDecision.ALLOW,
                rejection_reason="Simulated timeout",
                retry_count=0,
                duplicate_request_status=False,
                stdout="",
                stderr="simulated timeout",
                normalized_payload={"safe_execution_id": safe_exec_id},
            )
            audit_store.save_result(env)
            return env

        if fixture_id == SimulatedFixture.PROVIDER_REJECTION.value:
            env = rejected_provider_result(
                request,
                reason="simulated provider rejected the request",
                failure_class=FailureClass.POLICY_REJECTED,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                argv=argv,
            )
            audit_store.save_result(env)
            return env

        if fixture_id == SimulatedFixture.NONZERO_EXIT.value:
            env = ProviderResultEnvelope(
                schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
                request_id=request.request_id,
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                provider_cli_version="simulated-3b.1",
                task_id=request.task_id,
                plan_id=request.plan_id,
                project_id=request.project_id,
                session_id=request.session_id,
                worktree_id=request.worktree_id,
                role=request.role,
                invocation_mode=request.invocation_mode.value,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                sanitized_argument_array=argv,
                request_fingerprint=request.request_fingerprint(),
                context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
                approved_plan_fingerprint=request.approved_plan_fingerprint,
                starting_commit=request.starting_commit,
                started_at=started_at,
                finished_at=utc_now_iso(),
                duration_seconds=round(time.perf_counter() - started, 6),
                exit_code=7,
                timeout_status=False,
                cancellation_status=False,
                stdout_truncated=False,
                stderr_truncated=False,
                provider_result_status=ProviderResultStatus.FAILED,
                failure_class=FailureClass.NONZERO_EXIT,
                result_artifact_path=None,
                result_fingerprint=None,
                policy_decision=PolicyDecision.ALLOW,
                rejection_reason="Simulated nonzero exit",
                retry_count=0,
                duplicate_request_status=False,
                stderr="exit 7",
                normalized_payload={"safe_execution_id": safe_exec_id},
            )
            audit_store.save_result(env)
            return env

        if fixture_id == SimulatedFixture.MISSING_ARTIFACT.value:
            env = ProviderResultEnvelope(
                schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
                request_id=request.request_id,
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                provider_cli_version="simulated-3b.1",
                task_id=request.task_id,
                plan_id=request.plan_id,
                project_id=request.project_id,
                session_id=request.session_id,
                worktree_id=request.worktree_id,
                role=request.role,
                invocation_mode=request.invocation_mode.value,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                sanitized_argument_array=argv,
                request_fingerprint=request.request_fingerprint(),
                context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
                approved_plan_fingerprint=request.approved_plan_fingerprint,
                starting_commit=request.starting_commit,
                started_at=started_at,
                finished_at=utc_now_iso(),
                duration_seconds=round(time.perf_counter() - started, 6),
                exit_code=0,
                timeout_status=False,
                cancellation_status=False,
                stdout_truncated=False,
                stderr_truncated=False,
                provider_result_status=ProviderResultStatus.FAILED,
                failure_class=FailureClass.MISSING_ARTIFACT,
                result_artifact_path=None,
                result_fingerprint=None,
                policy_decision=PolicyDecision.ALLOW,
                rejection_reason="Expected result artifact missing",
                retry_count=0,
                duplicate_request_status=False,
                normalized_payload={"safe_execution_id": safe_exec_id},
            )
            audit_store.save_result(env)
            return env

        if fixture_id in (
            SimulatedFixture.MALFORMED_OUTPUT.value,
            SimulatedFixture.MALFORMED_REVIEW.value,
        ):
            # Persist a deliberately incomplete artifact; normalize fails closed.
            bad_path = audit_store.artifact_path(request.request_id, "malformed.json")
            bad_path.write_text("{not-json", encoding="utf-8")
            env = ProviderResultEnvelope(
                schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
                request_id=request.request_id,
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                provider_cli_version="simulated-3b.1",
                task_id=request.task_id,
                plan_id=request.plan_id,
                project_id=request.project_id,
                session_id=request.session_id,
                worktree_id=request.worktree_id,
                role=request.role,
                invocation_mode=request.invocation_mode.value,
                automation_status=AUTOMATION_SIMULATED,
                executable_identity="simulated",
                sanitized_argument_array=argv,
                request_fingerprint=request.request_fingerprint(),
                context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
                approved_plan_fingerprint=request.approved_plan_fingerprint,
                starting_commit=request.starting_commit,
                started_at=started_at,
                finished_at=utc_now_iso(),
                duration_seconds=round(time.perf_counter() - started, 6),
                exit_code=0,
                timeout_status=False,
                cancellation_status=False,
                stdout_truncated=False,
                stderr_truncated=False,
                provider_result_status=ProviderResultStatus.FAILED,
                failure_class=FailureClass.MALFORMED_OUTPUT,
                result_artifact_path=str(bad_path),
                result_fingerprint=None,
                policy_decision=PolicyDecision.DENY,
                rejection_reason="Malformed provider output failed closed",
                retry_count=0,
                duplicate_request_status=False,
                stdout="{not-json",
                normalized_payload={"safe_execution_id": safe_exec_id},
            )
            audit_store.save_result(env)
            return env

        payload = dict(FIXTURE_PAYLOADS.get(fixture_id, FIXTURE_PAYLOADS[SimulatedFixture.SUCCESS_IMPL.value]))
        artifact = audit_store.artifact_path(request.request_id, "result.json")
        text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        limit = request.output_limit_bytes
        stdout_trunc = False
        if fixture_id == SimulatedFixture.TRUNCATED_OUTPUT.value or len(text.encode()) > limit:
            raw = text.encode("utf-8", errors="replace")[:limit]
            text_out = raw.decode("utf-8", errors="replace") + "\n...[truncated]..."
            stdout_trunc = True
        else:
            text_out = text
        artifact.write_text(text, encoding="utf-8")
        result_fp = fingerprint(payload)

        env = ProviderResultEnvelope(
            schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
            request_id=request.request_id,
            provider_id=self.provider_id,
            adapter_version=self.adapter_version,
            provider_cli_version="simulated-3b.1",
            task_id=request.task_id,
            plan_id=request.plan_id,
            project_id=request.project_id,
            session_id=request.session_id,
            worktree_id=request.worktree_id,
            role=request.role,
            invocation_mode=request.invocation_mode.value,
            automation_status=AUTOMATION_SIMULATED,
            executable_identity="simulated",
            sanitized_argument_array=argv,
            request_fingerprint=request.request_fingerprint(),
            context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
            approved_plan_fingerprint=request.approved_plan_fingerprint,
            starting_commit=request.starting_commit,
            started_at=started_at,
            finished_at=utc_now_iso(),
            duration_seconds=round(time.perf_counter() - started, 6),
            exit_code=0,
            timeout_status=False,
            cancellation_status=False,
            stdout_truncated=stdout_trunc,
            stderr_truncated=False,
            provider_result_status=ProviderResultStatus.SUCCESS,
            failure_class=FailureClass.NONE,
            result_artifact_path=str(artifact),
            result_fingerprint=result_fp,
            policy_decision=PolicyDecision.ALLOW,
            rejection_reason=None,
            retry_count=0,
            duplicate_request_status=False,
            stdout=text_out[: min(len(text_out), limit)],
            normalized_payload={**payload, "safe_execution_id": safe_exec_id},
        )
        audit_store.save_result(env)
        return env
