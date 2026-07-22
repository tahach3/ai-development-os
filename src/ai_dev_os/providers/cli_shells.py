"""Shared helpers for real provider CLI adapter shells (no live by default)."""

from __future__ import annotations

from typing import Any

from ..provider_config import ProviderConfig
from ..provider_discovery import discover_provider
from ..provider_models import (
    AUTOMATION_DISCOVERY,
    AUTOMATION_DISABLED,
    AUTOMATION_MANUAL,
    AuthCategory,
    AvailabilityStatus,
    FailureClass,
    InstallationStatus,
    NetworkUse,
    PROVIDER_ADAPTER_VERSION,
    PolicyDecision,
    ProviderCapability,
    ProviderMode,
    ProviderRequest,
    ProviderResultStatus,
    rejected_provider_result,
)
from ..provider_audit import ProviderAuditStore
from .base import ProviderAdapter


def capability_from_discovery(
    *,
    provider_id: str,
    config: ProviderConfig,
    discovery: dict[str, Any],
    supported_roles: list[str],
    notes: str,
    supports_noninteractive_when_detected: bool,
) -> ProviderCapability:
    mode = config.effective_mode(provider_id)
    install = InstallationStatus(
        str(discovery.get("installation_status") or InstallationStatus.NOT_INSTALLED.value)
    )
    exe = discovery.get("executable")
    version = discovery.get("detected_version")
    if isinstance(version, str) or version is None:
        detected_version = version
    else:
        detected_version = str(version) if version else None

    if mode is ProviderMode.DISABLED:
        availability = AvailabilityStatus.DISABLED
        automation = AUTOMATION_DISABLED
    elif install is InstallationStatus.AMBIGUOUS:
        availability = AvailabilityStatus.MANUAL_ONLY
        automation = AUTOMATION_MANUAL
    elif install is InstallationStatus.DETECTED:
        if mode is ProviderMode.DISCOVERY_ONLY:
            availability = AvailabilityStatus.DISCOVERY_READY
            automation = AUTOMATION_DISCOVERY
        elif mode is ProviderMode.MANUAL_HANDOFF:
            availability = AvailabilityStatus.MANUAL_ONLY
            automation = AUTOMATION_MANUAL
        elif mode is ProviderMode.LIVE_LOCAL_CLI_ALLOWED:
            availability = AvailabilityStatus.LIVE_GATED
            automation = AUTOMATION_DISCOVERY
        else:
            availability = AvailabilityStatus.DISCOVERY_READY
            automation = AUTOMATION_DISCOVERY
    else:
        availability = AvailabilityStatus.MANUAL_ONLY
        automation = AUTOMATION_MANUAL

    noninteractive = bool(
        supports_noninteractive_when_detected
        and install is InstallationStatus.DETECTED
        and mode is not ProviderMode.DISABLED
    )
    # Cursor: never claim noninteractive unless discovery proved version cleanly.
    if provider_id == "cursor":
        if install is not InstallationStatus.DETECTED or not detected_version:
            noninteractive = False
            availability = AvailabilityStatus.MANUAL_ONLY
            automation = AUTOMATION_MANUAL

    return ProviderCapability(
        provider_id=provider_id,
        adapter_version=PROVIDER_ADAPTER_VERSION,
        executable_identity=str(exe) if exe else provider_id,
        detected_version=detected_version,
        installation_status=install,
        availability_status=availability,
        supported_roles=supported_roles,
        supported_modes=[
            ProviderMode.DISABLED.value,
            ProviderMode.DISCOVERY_ONLY.value,
            ProviderMode.MANUAL_HANDOFF.value,
            ProviderMode.LIVE_LOCAL_CLI_ALLOWED.value,
        ],
        supports_noninteractive=noninteractive,
        supports_stdin_prompt=False,
        supports_file_prompt=True,
        auth_category=AuthCategory.ASSUMED_EXTERNAL_CLI_SESSION
        if install is InstallationStatus.DETECTED
        else AuthCategory.UNKNOWN,
        network_use=NetworkUse.MAY_CONTACT_PROVIDER_BACKEND
        if install is InstallationStatus.DETECTED
        else NetworkUse.UNKNOWN,
        live_execution_permission=False,
        automation_status=automation,
        notes=notes + " " + str(discovery.get("note") or ""),
    )


class CliAdapterShell(ProviderAdapter):
    """Detect / preview / discover only — live refused by default."""

    provider_id: str
    display_basename: str
    supported_roles: list[str]
    default_notes: str
    supports_noninteractive_when_detected: bool = True

    def describe_capabilities(
        self,
        *,
        config: ProviderConfig,
        discovery: dict[str, Any] | None = None,
    ) -> ProviderCapability:
        entry = config.get_entry(self.provider_id)
        disc = discovery or discover_provider(
            self.provider_id, configured_path=entry.executable_path
        )
        return capability_from_discovery(
            provider_id=self.provider_id,
            config=config,
            discovery=disc,
            supported_roles=self.supported_roles,
            notes=self.default_notes,
            supports_noninteractive_when_detected=self.supports_noninteractive_when_detected,
        )

    def preview_invocation(self, request: ProviderRequest) -> dict[str, Any]:
        # Preview never includes credentials; file-path handoff only.
        context = request.context_artifact_path or "<context-artifact>"
        argv = [
            self.display_basename,
            "preview",
            "--role",
            request.role,
            "--context-file",
            context,
            "--request-id",
            request.request_id,
        ]
        return {
            "provider_id": self.provider_id,
            "mode": request.invocation_mode.value,
            "executable_identity": self.display_basename,
            "sanitized_argument_array": argv,
            "live_model_call": False,
            "request_fingerprint": request.request_fingerprint(),
            "note": "Preview only; live model execution not authorized by default.",
        }

    def execute(
        self,
        request: ProviderRequest,
        *,
        config: ProviderConfig,
        audit_store: ProviderAuditStore,
        confinement_root: str | None = None,
    ):
        preview = self.preview_invocation(request)
        mode = config.effective_mode(self.provider_id)

        if request.invocation_mode is ProviderMode.DISCOVERY_ONLY or mode is ProviderMode.DISCOVERY_ONLY:
            entry = config.get_entry(self.provider_id)
            disc = discover_provider(self.provider_id, configured_path=entry.executable_path)
            from ..provider_models import (
                AUTOMATION_DISCOVERY,
                PROVIDER_RESULT_SCHEMA_VERSION,
                ProviderResultEnvelope,
            )
            from ..models import utc_now_iso

            now = utc_now_iso()
            env = ProviderResultEnvelope(
                schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
                request_id=request.request_id,
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                provider_cli_version=disc.get("detected_version")
                if isinstance(disc.get("detected_version"), str)
                else None,
                task_id=request.task_id,
                plan_id=request.plan_id,
                project_id=request.project_id,
                session_id=request.session_id,
                worktree_id=request.worktree_id,
                role=request.role,
                invocation_mode=request.invocation_mode.value,
                automation_status=AUTOMATION_DISCOVERY,
                executable_identity=str(disc.get("executable") or self.display_basename),
                sanitized_argument_array=list(preview["sanitized_argument_array"]),
                request_fingerprint=request.request_fingerprint(),
                context_or_handoff_fingerprint=request.context_or_handoff_fingerprint,
                approved_plan_fingerprint=request.approved_plan_fingerprint,
                starting_commit=request.starting_commit,
                started_at=now,
                finished_at=now,
                duration_seconds=0.0,
                exit_code=0,
                timeout_status=False,
                cancellation_status=False,
                stdout_truncated=False,
                stderr_truncated=False,
                provider_result_status=ProviderResultStatus.SUCCESS,
                failure_class=FailureClass.NONE,
                result_artifact_path=None,
                result_fingerprint=None,
                policy_decision=PolicyDecision.ALLOW,
                rejection_reason=None,
                retry_count=0,
                duplicate_request_status=False,
                stdout="",
                stderr="",
                normalized_payload={
                    "discovery": {
                        k: disc[k]
                        for k in (
                            "provider_id",
                            "executable",
                            "installation_status",
                            "detected_version",
                            "note",
                            "discovery_ran",
                            "live_model_call",
                        )
                        if k in disc
                    }
                },
            )
            audit_store.save_result(env)
            return env

        if request.invocation_mode is ProviderMode.MANUAL_HANDOFF or mode is ProviderMode.MANUAL_HANDOFF:
            env = rejected_provider_result(
                request,
                reason="manual_handoff mode: use prepare-handoff; no CLI spawn",
                failure_class=FailureClass.POLICY_REJECTED,
                automation_status=AUTOMATION_MANUAL,
                executable_identity=self.display_basename,
                argv=list(preview["sanitized_argument_array"]),
            )
            # Not really a hard failure for operators — mark as rejected spawn with manual status.
            audit_store.save_result(env)
            return env

        # Live and any other execute path: refuse in Round 3B default.
        env = rejected_provider_result(
            request,
            reason=(
                "Live provider model execution is not authorized; "
                "adapter shell supports detect/preview/discovery/simulated only"
            ),
            failure_class=FailureClass.POLICY_REJECTED,
            automation_status=AUTOMATION_DISABLED,
            executable_identity=self.display_basename,
            argv=list(preview["sanitized_argument_array"]),
        )
        audit_store.save_result(env)
        return env


class ClaudeCodeCliAdapter(CliAdapterShell):
    provider_id = "claude_code"
    adapter_version = PROVIDER_ADAPTER_VERSION
    display_basename = "claude"
    supported_roles = ["claude"]
    default_notes = (
        "Adapter implemented. CLI detection via PATH/--version only. "
        "Live execution not authorized."
    )
    supports_noninteractive_when_detected = True


class CodexCliAdapter(CliAdapterShell):
    provider_id = "codex"
    adapter_version = PROVIDER_ADAPTER_VERSION
    display_basename = "codex"
    supported_roles = ["codex"]
    default_notes = (
        "Adapter implemented. CLI detection via PATH/--version only. "
        "Live execution not authorized."
    )
    supports_noninteractive_when_detected = True


class CursorCliAdapter(CliAdapterShell):
    provider_id = "cursor"
    adapter_version = PROVIDER_ADAPTER_VERSION
    display_basename = "cursor"
    supported_roles = ["cursor"]
    default_notes = (
        "Adapter implemented. Cursor desktop app is not assumed to provide "
        "automation-compatible CLI. Non-interactive agent execution is not claimed "
        "unless discovery proves it. Manual handoff remains available. "
        "Live execution not authorized."
    )
    # Do not claim noninteractive merely because `cursor` exists on PATH.
    supports_noninteractive_when_detected = False
