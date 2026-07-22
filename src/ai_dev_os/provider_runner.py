"""High-level provider request lifecycle: validate, preview, simulate, cancel."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .context_builder import build_context_packet
from .fingerprints import fingerprint_context_manifest, fingerprint_plan
from .models import ModelRole
from .plan_store import PlanStore
from .project_registry import ProjectRegistry
from .provider_audit import ProviderAuditStore
from .provider_config import ProviderConfig, load_provider_config
from .provider_models import ProviderMode
from .provider_discovery import discover_provider
from .provider_models import (
    AUTOMATION_DISABLED,
    FailureClass,
    ProviderRequest,
    ProviderResultEnvelope,
    ProviderResultStatus,
    SimulatedFixture,
    is_provider_result_intake_ready,
    rejected_provider_result,
    validate_provider_result_dict,
)
from .provider_policy import ProviderPolicyError, assert_may_run_provider, assert_live_gates
from .providers import get_provider_adapter, list_provider_ids
from .safe_policy import DEFAULT_OUTPUT_LIMIT_BYTES, DEFAULT_TIMEOUT_SECONDS, PolicyError
from .session_store import SessionStore
from .task_store import TaskStore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class ProviderRunner:
    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        registry: ProjectRegistry | None = None,
        config: ProviderConfig | None = None,
        task_store: TaskStore | None = None,
        plan_store: PlanStore | None = None,
        session_store: SessionStore | None = None,
        audit_store: ProviderAuditStore | None = None,
    ) -> None:
        self.workspace_root = workspace_root or (_repo_root() / "workspace")
        self.registry = registry or ProjectRegistry()
        self.config = config or load_provider_config()
        self.task_store = task_store or TaskStore()
        self.plan_store = plan_store or PlanStore()
        self.session_store = session_store or SessionStore(
            workspace_root=self.workspace_root, registry=self.registry
        )
        self.audit_store = audit_store or ProviderAuditStore(
            workspace_root=self.workspace_root
        )

    def list_adapters(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pid in list_provider_ids():
            adapter = get_provider_adapter(pid)
            entry = self.config.get_entry(pid)
            disc = None
            if pid != "simulated":
                disc = discover_provider(pid, configured_path=entry.executable_path)
            cap = adapter.describe_capabilities(config=self.config, discovery=disc)
            rows.append(
                {
                    "provider_id": pid,
                    "adapter_version": adapter.adapter_version,
                    "effective_mode": self.config.effective_mode(pid).value,
                    "capabilities": cap.to_dict(),
                }
            )
        return rows

    def show_capabilities(self, provider_id: str) -> dict[str, Any]:
        adapter = get_provider_adapter(provider_id)
        entry = self.config.get_entry(provider_id)
        disc = (
            None
            if provider_id == "simulated"
            else discover_provider(provider_id, configured_path=entry.executable_path)
        )
        return adapter.describe_capabilities(config=self.config, discovery=disc).to_dict()

    def discover_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for pid in list_provider_ids():
            entry = self.config.get_entry(pid)
            results.append(
                discover_provider(pid, configured_path=entry.executable_path)
            )
        return results

    def build_request(
        self,
        *,
        provider_id: str,
        task_id: str,
        plan_id: str,
        session_id: str,
        role: str | None = None,
        invocation_mode: ProviderMode = ProviderMode.SIMULATED,
        fixture_id: str | None = None,
        timeout_seconds: float | None = None,
        output_limit_bytes: int | None = None,
        request_id: str | None = None,
    ) -> ProviderRequest:
        task = self.task_store.load(task_id)
        plan = self.plan_store.load(plan_id)
        session = self.session_store.load(session_id)

        assigned_role = role or (
            task.assigned_role.value if task.assigned_role else ModelRole.CURSOR.value
        )
        project = self.registry.require(task.project_id)
        packet = build_context_packet(task, project.root_path)
        ctx_fp = fingerprint_context_manifest(packet.manifest)
        meta = dict(task.metadata or {})
        meta["context_or_handoff_fingerprint"] = ctx_fp
        task.metadata = meta
        self.task_store.update(task)

        approved_fp = plan.approved_fingerprint or fingerprint_plan(plan.to_dict())
        adapter = get_provider_adapter(provider_id)
        rid = request_id or f"preq-{uuid.uuid4().hex[:12]}"

        req = ProviderRequest(
            request_id=rid,
            provider_id=provider_id,
            adapter_version=adapter.adapter_version,
            task_id=task_id,
            plan_id=plan_id,
            approved_plan_fingerprint=str(approved_fp),
            project_id=task.project_id,
            session_id=session_id,
            worktree_id=str(Path(session.worktree_path).resolve()),
            starting_commit=session.starting_commit,
            role=assigned_role,
            context_or_handoff_fingerprint=ctx_fp,
            invocation_mode=invocation_mode,
            timeout_seconds=float(
                timeout_seconds
                if timeout_seconds is not None
                else DEFAULT_TIMEOUT_SECONDS
            ),
            output_limit_bytes=int(
                output_limit_bytes
                if output_limit_bytes is not None
                else DEFAULT_OUTPUT_LIMIT_BYTES
            ),
            fixture_id=fixture_id,
            context_artifact_path=None,
        )
        self.audit_store.save_request(req)
        return req

    def validate_request(self, request: ProviderRequest) -> dict[str, Any]:
        try:
            assert_may_run_provider(
                request,
                config=self.config,
                task_store=self.task_store,
                plan_store=self.plan_store,
                session_store=self.session_store,
                registry=self.registry,
            )
            return {
                "valid": True,
                "request_id": request.request_id,
                "request_fingerprint": request.request_fingerprint(),
                "errors": [],
            }
        except (ProviderPolicyError, PolicyError, KeyError, FileNotFoundError) as exc:
            failure = getattr(exc, "failure_class", FailureClass.POLICY_REJECTED)
            return {
                "valid": False,
                "request_id": request.request_id,
                "request_fingerprint": request.request_fingerprint(),
                "errors": [str(exc)],
                "failure_class": failure.value
                if hasattr(failure, "value")
                else str(failure),
            }

    def preview_invocation(self, request: ProviderRequest) -> dict[str, Any]:
        adapter = get_provider_adapter(request.provider_id)
        return adapter.preview_invocation(request)

    def run_simulated(
        self,
        request: ProviderRequest,
        *,
        fixture_id: str | None = None,
    ) -> ProviderResultEnvelope:
        if request.invocation_mode is not ProviderMode.SIMULATED:
            env = rejected_provider_result(
                request,
                reason="run_simulated requires invocation_mode=simulated",
                automation_status=AUTOMATION_DISABLED,
            )
            self.audit_store.save_result(env)
            return env

        # Ensure simulated provider enabled in config for this run path.
        effective = self.config.effective_mode(request.provider_id)
        if request.provider_id != "simulated" and effective is not ProviderMode.SIMULATED:
            # Real CLI shells should not silently become live; only simulated provider runs fixtures.
            if request.provider_id != "simulated":
                env = rejected_provider_result(
                    request,
                    reason="Simulated fixtures are only executed by the simulated provider",
                    automation_status=AUTOMATION_DISABLED,
                )
                self.audit_store.save_result(env)
                return env

        if fixture_id:
            request.fixture_id = fixture_id
            self.audit_store.save_request(request)

        # Fixture ids that synthesize stale/cancel outcomes inside the adapter
        # still go through the adapter after a soft binding check when possible.
        synthetic_fixture = request.fixture_id in {
            SimulatedFixture.STALE_PLAN.value,
            SimulatedFixture.STALE_COMMIT.value,
            SimulatedFixture.CANCELLED.value,
            SimulatedFixture.DUPLICATE_REQUEST.value,
        }

        confinement: str | None = None
        try:
            _task, _plan, session = assert_may_run_provider(
                request,
                config=self.config,
                task_store=self.task_store,
                plan_store=self.plan_store,
                session_store=self.session_store,
                registry=self.registry,
            )
            confinement = str(Path(session.worktree_path).resolve())
        except ProviderPolicyError as exc:
            if synthetic_fixture and request.provider_id == "simulated":
                session = self.session_store.load(request.session_id)
                confinement = str(Path(session.worktree_path).resolve())
            else:
                env = rejected_provider_result(
                    request,
                    reason=str(exc),
                    failure_class=exc.failure_class,
                    automation_status=AUTOMATION_DISABLED,
                )
                self.audit_store.save_result(env)
                return env
        except (PolicyError, KeyError, FileNotFoundError) as exc:
            env = rejected_provider_result(
                request,
                reason=str(exc),
                automation_status=AUTOMATION_DISABLED,
            )
            self.audit_store.save_result(env)
            return env

        adapter = get_provider_adapter(request.provider_id)
        # Simulated adapter has extra kwargs
        if request.provider_id == "simulated":
            result = adapter.execute(  # type: ignore[call-arg]
                request,
                config=self.config,
                audit_store=self.audit_store,
                confinement_root=confinement,
                workspace_root=self.workspace_root,
                run_safe_pytest=True,
            )
        else:
            result = adapter.execute(
                request,
                config=self.config,
                audit_store=self.audit_store,
                confinement_root=confinement,
            )
        return result

    def refuse_live(self, request: ProviderRequest) -> ProviderResultEnvelope:
        try:
            assert_live_gates(
                request,
                config=self.config,
                task_store=self.task_store,
                plan_store=self.plan_store,
                session_store=self.session_store,
                registry=self.registry,
            )
        except ProviderPolicyError as exc:
            env = rejected_provider_result(
                request,
                reason=str(exc),
                failure_class=exc.failure_class,
                automation_status=AUTOMATION_DISABLED,
            )
            self.audit_store.save_result(env)
            return env
        env = rejected_provider_result(
            request,
            reason="Live provider model execution is not authorized",
            automation_status=AUTOMATION_DISABLED,
        )
        self.audit_store.save_result(env)
        return env

    def show_status(self, request_id: str) -> dict[str, Any]:
        req = self.audit_store.load_request(request_id)
        status: dict[str, Any] = {
            "request_id": request_id,
            "provider_id": req.provider_id,
            "invocation_mode": req.invocation_mode.value,
            "request_fingerprint": req.request_fingerprint(),
            "task_id": req.task_id,
            "plan_id": req.plan_id,
            "project_id": req.project_id,
            "session_id": req.session_id,
            "role": req.role,
            "cancel_requested": self.audit_store.is_cancel_requested(request_id),
            "result": None,
        }
        try:
            result = self.audit_store.load_result(request_id)
            status["result"] = {
                "provider_result_status": result.provider_result_status.value,
                "failure_class": result.failure_class.value,
                "policy_decision": result.policy_decision.value,
                "automation_status": result.automation_status,
                "duplicate_request_status": result.duplicate_request_status,
                "timeout_status": result.timeout_status,
                "cancellation_status": result.cancellation_status,
                "result_artifact_path": result.result_artifact_path,
                "rejection_reason": result.rejection_reason,
            }
        except FileNotFoundError:
            pass
        return status

    def show_result(self, request_id: str) -> ProviderResultEnvelope:
        return self.audit_store.load_result(request_id)

    def cancel(self, request_id: str) -> dict[str, Any]:
        self.audit_store.load_request(request_id)
        self.audit_store.request_cancel(request_id)
        # If result not yet written, a subsequent simulated cancel fixture will honor it.
        try:
            existing = self.audit_store.load_result(request_id)
            return {
                "request_id": request_id,
                "cancel_requested": True,
                "already_finished": True,
                "provider_result_status": existing.provider_result_status.value,
            }
        except FileNotFoundError:
            return {
                "request_id": request_id,
                "cancel_requested": True,
                "already_finished": False,
            }

    def intake_ready(self, request_id: str) -> dict[str, Any]:
        envelope = self.audit_store.load_result(request_id)
        errors = validate_provider_result_dict(envelope.to_dict())
        ready = is_provider_result_intake_ready(envelope) and not errors
        return {
            "request_id": request_id,
            "intake_ready": ready,
            "errors": errors,
            "provider_result_status": envelope.provider_result_status.value,
        }
