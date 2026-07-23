"""Provider readiness audit engine (Round 4D1) — discovery/version/help/auth only."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any, Sequence

from .fingerprints import fingerprint
from .models import utc_now_iso
from .provider_config import ProviderConfig, fail_closed_default_config, load_provider_config
from .provider_models import PROVIDER_ADAPTER_VERSION, ProviderMode
from .provider_readiness_constants import (
    AUTHENTICATION_MODE_POLICY_VERSION,
    HELP_SUMMARY_LIMIT,
    READINESS_POLICY_VERSION,
    READINESS_SCHEMA_VERSION,
)
from .provider_readiness_discovery import discover_executable_candidates
from .provider_readiness_models import (
    AuditEvent,
    AuditEventType,
    AuthenticationStatus,
    CapabilityStatus,
    CompatibilityStatus,
    DiscoveryStatus,
    NoninteractiveStatus,
    ProviderReadinessRecord,
    ReadinessAuditBundle,
    empty_record,
    new_audit_id,
)
from .provider_readiness_policy import (
    aggregate_verdict,
    capability_from_adapter_contract,
    decide_provider_verdict,
)
from .provider_readiness_auth import resolve_auth_probe_plan
from .provider_readiness_host_verdict import compute_host_system_verdict
from .provider_readiness_noninteractive import assess_noninteractive_contract
from .provider_readiness_probes import interpret_auth_probe, probe_provider
from .provider_readiness_profiles import adapter_version_for, get_profile, version_compatible
from .provider_readiness_roles import (
    build_role_matrix,
    compute_independence,
    role_eligibility,
)
from .providers import list_provider_ids
from .safe_policy import PolicyError, assert_not_equitify_blob


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head(repo: Path) -> str:
    try:
        import subprocess

        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
        )
        if completed.returncode == 0:
            return (completed.stdout or "").strip()
    except OSError:
        pass
    return "unknown"


def _repository_identity(repo: Path) -> str:
    try:
        import subprocess

        completed = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
        )
        if completed.returncode == 0:
            url = (completed.stdout or "").strip()
            # Sanitize to host/path without credentials.
            if "github.com" in url:
                return "github.com/tahach3/ai-development-os"
            return "git-remote-configured"
    except OSError:
        pass
    return str(repo.name)


class ProviderReadinessEngine:
    """Orchestrates safe readiness audits. Never invokes live model prompts."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        config: ProviderConfig | None = None,
        registry: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else _repo_root()
        self.config = config
        self.registry = registry
        self._live_invocations = 0

    def _load_config(self) -> ProviderConfig:
        if self.config is not None:
            return self.config
        try:
            return load_provider_config()
        except Exception:
            return fail_closed_default_config()

    def _assert_project(self, project_id: str) -> Any:
        assert_not_equitify_blob(project_id)
        if "equitify" in project_id.lower():
            raise PolicyError("Equitify projects are disconnected and refused")
        if self.registry is None:
            from .project_registry import ProjectRegistry

            self.registry = ProjectRegistry()
        return self.registry.require(project_id)

    def audit_provider(
        self,
        provider_id: str,
        *,
        project_id: str,
        include_help_summary: bool = False,
        path_env: str | None = None,
        allow_unknown_auth_conditional: bool = False,
        enable_where: bool = True,
        enable_get_command: bool = True,
        probe_timeout: float | None = None,
        synthetic_overrides: dict[str, Any] | None = None,
    ) -> ProviderReadinessRecord:
        project = self._assert_project(project_id)
        assert_not_equitify_blob(provider_id, project.id, project.root_path)
        config = self._load_config()
        profile = get_profile(provider_id)
        adapter_version = adapter_version_for(provider_id)
        host = platform.system().lower()
        commit = _git_head(self.repo_root)
        repo_id = _repository_identity(self.repo_root)
        record = empty_record(
            provider_id=provider_id,
            project_id=project_id,
            repository_identity=repo_id,
            repository_commit=commit,
            host_platform=host,
            adapter_version=adapter_version,
        )
        events: list[AuditEvent] = []
        events.append(
            AuditEvent(
                event_type=AuditEventType.LIVE_INVOCATION_BLOCKED.value,
                message="Round 4D1 readiness never invokes live providers",
                provider_id=provider_id,
                details={"live_provider_invocations": 0},
            )
        )

        mode = config.effective_mode(provider_id)
        record.provider_mode_configuration = mode.value
        record.live_policy_status = "disabled_for_round_4d1"
        record.supported_roles = list(profile.adapter_roles)

        overrides = synthetic_overrides or {}

        if provider_id == "simulated" and not overrides.get("force_assess_simulated"):
            record.discovery_status = DiscoveryStatus.NOT_INSTALLED.value
            record.final_readiness_verdict = "no_eligible_provider"
            record.blockers = ["simulated_provider_not_eligible_for_live_smoke"]
            record.noninteractive_status = NoninteractiveStatus.SUPPORTED_VERIFIED.value
            record.noninteractive_evidence = "simulated_fixture_contract"
            record.authentication_status = AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
            record.warnings = ["simulation_is_not_live_execution"]
            record.audit_events = [e.to_dict() for e in events]
            record.source_fingerprints = {
                "provider_config": fingerprint(config.sanitized_public_dict()),
                "project_registration": fingerprint(
                    {"id": project.id, "root_path": project.root_path}
                ),
                "readiness_policy": READINESS_POLICY_VERSION,
            }
            record.record_fingerprint = record.compute_fingerprint()
            return record

        entry = config.get_entry(provider_id)
        configured_path = entry.executable_path

        # Host-local pin overlay (ignored runtime; never enables live).
        pin_meta: dict[str, Any] = {}
        try:
            # Unused import cleanup in pin block
            from .provider_readiness_pins import ProviderPinStore, validate_pin

            pin_store = ProviderPinStore(self.repo_root / "workspace" / "provider_pins")
            pin = pin_store.load(provider_id)
            if pin is not None:
                pin_result = validate_pin(
                    pin,
                    adapter_version=adapter_version,
                )
                pin_meta = pin_result.to_dict()
                if pin_result.valid:
                    configured_path = pin.canonical_executable_path
                    events.append(
                        AuditEvent(
                            event_type=AuditEventType.PIN_VALIDATED.value,
                            message="Host-local executable pin validated",
                            provider_id=provider_id,
                            details={"candidate_id": pin.candidate_id},
                        )
                    )
                else:
                    events.append(
                        AuditEvent(
                            event_type=AuditEventType.PIN_REJECTED.value,
                            message="Host-local executable pin rejected",
                            provider_id=provider_id,
                            details={"reasons": pin_result.reasons},
                        )
                    )
        except Exception:
            pin_meta = {}

        discovery = discover_executable_candidates(
            provider_id,
            configured_path=configured_path,
            path_env=path_env,
            enable_where=enable_where if path_env is None else False,
            enable_get_command=enable_get_command if path_env is None else False,
        )
        # Test/synthetic path injection.
        if "discovery" in overrides:
            discovery = overrides["discovery"]

        record.discovery_status = discovery.status.value
        record.candidate_executables = [c.to_dict() for c in discovery.candidates]
        record.duplicate_executable_count = discovery.duplicate_count
        record.selected_executable_rule = discovery.selected_rule
        if discovery.ambiguity:
            record.metadata["ambiguity_resolution"] = discovery.ambiguity
            for ev in (discovery.ambiguity.get("audit_events") or []):
                if isinstance(ev, dict):
                    events.append(
                        AuditEvent(
                            event_type=str(ev.get("event_type") or "candidate_discovered"),
                            message=str(ev.get("message") or ""),
                            provider_id=provider_id,
                            details=dict(ev.get("details") or {}),
                        )
                    )
            if discovery.ambiguity.get("requires_operator_selection"):
                from .provider_readiness_selection import build_operator_decision

                # Rebuild typed resolution for decision record from candidates.
                from .provider_readiness_ambiguity import resolve_ambiguity

                resolution = resolve_ambiguity(provider_id, discovery.candidates)
                if resolution.requires_operator_selection:
                    decision = build_operator_decision(resolution)
                    record.metadata["operator_decision"] = decision.to_dict()
                    events.append(
                        AuditEvent(
                            event_type=AuditEventType.SELECTION_REQUIRED.value,
                            message="Distinct trusted installations require operator selection",
                            provider_id=provider_id,
                            details={
                                "decision_id": decision.decision_id,
                                "recommended_candidate_id": decision.recommended_candidate_id,
                            },
                        )
                    )
                    events.append(
                        AuditEvent(
                            event_type=AuditEventType.RECOMMENDATION_PRODUCED.value,
                            message="Recommendation produced without automatic selection",
                            provider_id=provider_id,
                            details={
                                "recommended_candidate_id": decision.recommended_candidate_id,
                                "reasons": decision.recommendation_reasons,
                            },
                        )
                    )
        if pin_meta:
            record.metadata["executable_pin"] = pin_meta
        if discovery.selected:
            events.append(
                AuditEvent(
                    event_type=AuditEventType.EXECUTABLE_DISCOVERED.value,
                    message="Trusted executable candidate selected",
                    provider_id=provider_id,
                    details={
                        "basename": discovery.selected.basename,
                        "fingerprint": discovery.selected.fingerprint,
                        "location": discovery.selected.sanitized_location,
                    },
                )
            )
            record.executable_name = discovery.selected.basename
            record.sanitized_executable_location = discovery.selected.sanitized_location
            record.executable_fingerprint = discovery.selected.fingerprint
            record.executable_provenance = discovery.selected.resolution_method
        if discovery.duplicate_count > 1:
            events.append(
                AuditEvent(
                    event_type=AuditEventType.DUPLICATE_EXECUTABLE_DETECTED.value,
                    message="Multiple executable candidates detected",
                    provider_id=provider_id,
                    details={"count": discovery.duplicate_count},
                )
            )

        probes_out: list[dict[str, Any]] = []
        auth_status = AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
        auth_method = "none"
        auth_mode = "none"
        help_status = CompatibilityStatus.UNAVAILABLE.value
        version_status = CompatibilityStatus.UNAVAILABLE.value
        cli_version = None
        compat = CompatibilityStatus.UNAVAILABLE.value
        help_summary: str | None = None
        auth_plan = resolve_auth_probe_plan(
            profile_auth_argv=profile.auth_argv,
            auth_probe_mode=getattr(profile, "auth_probe_mode", "profile_only"),
            help_text=None,
        )

        if discovery.status is DiscoveryStatus.INSTALLED and discovery.selected:
            # First pass: version + help (help needed for auth plan when mode requires it).
            probes = probe_provider(
                discovery.selected.path,
                profile,
                adapter_version=adapter_version,
                executable_fingerprint=discovery.selected.fingerprint,
                include_help=include_help_summary,
                force_help_for_auth_plan=True,
                timeout=probe_timeout,
            )
            if "probes" in overrides:
                probes = overrides["probes"]

            version_probe = probes.get("version")
            if version_probe:
                events.append(
                    AuditEvent(
                        event_type=(
                            AuditEventType.PROBE_SKIPPED_BY_SAFETY_POLICY.value
                            if version_probe.skipped
                            else AuditEventType.VERSION_PROBE_ATTEMPTED.value
                        ),
                        message=version_probe.skip_reason or "version probe executed",
                        provider_id=provider_id,
                    )
                )
                probes_out.append(version_probe.to_dict())
                cli_version = version_probe.parsed_cli_version
                version_status = version_probe.parse_status
                if version_probe.failure_class == "timeout":
                    record.discovery_status = DiscoveryStatus.PROBE_FAILED.value

            help_probe = probes.get("help")
            if help_probe:
                events.append(
                    AuditEvent(
                        event_type=(
                            AuditEventType.PROBE_SKIPPED_BY_SAFETY_POLICY.value
                            if help_probe.skipped
                            else AuditEventType.HELP_PROBE_ATTEMPTED.value
                        ),
                        message=help_probe.skip_reason or "help probe executed",
                        provider_id=provider_id,
                    )
                )
                probes_out.append(help_probe.to_dict())
                if help_probe.skipped:
                    help_status = CompatibilityStatus.UNAVAILABLE.value
                elif help_probe.failure_class == "timeout":
                    help_status = CompatibilityStatus.UNAVAILABLE.value
                elif help_probe.exit_code == 0:
                    help_status = CompatibilityStatus.SUPPORTED.value
                    # Prefer raw-ish sanitized summary; keep enough for contract scans.
                    help_summary = (help_probe.sanitized_output_summary or "")[:HELP_SUMMARY_LIMIT]
                else:
                    help_status = CompatibilityStatus.UNVERIFIED.value
                    help_summary = (help_probe.sanitized_output_summary or "")[:HELP_SUMMARY_LIMIT]

            # If overrides supply help text, prefer that for planning (synthetic tests).
            if overrides.get("help_text"):
                help_summary = str(overrides["help_text"])[:HELP_SUMMARY_LIMIT]

            # Resolve auth plan from profile + help advertisement.
            auth_plan = resolve_auth_probe_plan(
                profile_auth_argv=profile.auth_argv,
                auth_probe_mode=getattr(profile, "auth_probe_mode", "profile_only"),
                help_text=help_summary,
            )
            events.append(
                AuditEvent(
                    event_type=(
                        AuditEventType.AUTH_STATUS_ADVERTISED.value
                        if auth_plan.advertised
                        else AuditEventType.AUTH_STATUS_NOT_ADVERTISED.value
                    ),
                    message=auth_plan.reason,
                    provider_id=provider_id,
                    details=auth_plan.to_dict(),
                )
            )

            # Run auth probe only when plan says runnable and initial auth was skipped.
            auth_probe = probes.get("auth")
            if auth_plan.runnable and auth_plan.argv and (auth_probe is None or auth_probe.skipped):
                auth_probe = probe_provider(
                    discovery.selected.path,
                    profile,
                    adapter_version=adapter_version,
                    executable_fingerprint=discovery.selected.fingerprint,
                    include_help=False,
                    auth_argv_override=auth_plan.argv,
                    timeout=probe_timeout,
                ).get("auth")
                if auth_probe:
                    probes["auth"] = auth_probe

            if auth_probe:
                events.append(
                    AuditEvent(
                        event_type=(
                            AuditEventType.PROBE_SKIPPED_BY_SAFETY_POLICY.value
                            if auth_probe.skipped
                            else AuditEventType.AUTHENTICATION_PROBE_ATTEMPTED.value
                        ),
                        message=auth_probe.skip_reason or "authentication probe executed",
                        provider_id=provider_id,
                    )
                )
                # Avoid duplicate auth entries if already present from first pass.
                if not any(p.get("kind") == "auth_status" for p in probes_out):
                    probes_out.append(auth_probe.to_dict())
                elif not auth_probe.skipped:
                    probes_out = [p for p in probes_out if p.get("kind") != "auth_status"]
                    probes_out.append(auth_probe.to_dict())
                if auth_probe.skipped:
                    auth_status = AuthenticationStatus.VERIFICATION_UNSUPPORTED.value
                    auth_method = "none"
                    auth_mode = "none"
                else:
                    auth_status, auth_method, auth_mode = interpret_auth_probe(auth_probe)

            compat = version_compatible(cli_version, profile)
            if overrides.get("authentication_status"):
                auth_status = overrides["authentication_status"]
                auth_method = overrides.get("authentication_verification_method", auth_method)
            if overrides.get("authentication_mode"):
                auth_mode = str(overrides["authentication_mode"])
            if overrides.get("compatibility_status"):
                compat = overrides["compatibility_status"]
            if overrides.get("cli_version"):
                cli_version = overrides["cli_version"]

        elif discovery.status is DiscoveryStatus.NOT_INSTALLED:
            pass
        elif discovery.status is DiscoveryStatus.AMBIGUOUS_INSTALLATION:
            pass

        # Apply auth/compat overrides for synthetic scenarios even without install.
        if overrides.get("authentication_status") and discovery.status is not DiscoveryStatus.INSTALLED:
            auth_status = overrides["authentication_status"]
            auth_method = overrides.get("authentication_verification_method", auth_method)
        if overrides.get("authentication_mode"):
            auth_mode = str(overrides["authentication_mode"])

        if overrides.get("help_text"):
            help_summary = str(overrides["help_text"])[:HELP_SUMMARY_LIMIT]
            auth_plan = resolve_auth_probe_plan(
                profile_auth_argv=profile.auth_argv,
                auth_probe_mode=getattr(profile, "auth_probe_mode", "profile_only"),
                help_text=help_summary,
            )

        record.probes = probes_out
        record.cli_version = cli_version
        record.version_verification_status = version_status
        record.compatibility_status = compat
        record.help_probe_status = help_status
        record.authentication_status = auth_status
        record.authentication_verification_method = auth_method
        record.authentication_mode = auth_mode
        record.auth_status_command_advertised = bool(auth_plan.advertised)
        record.auth_status_command_runnable = bool(auth_plan.runnable)
        record.metadata["auth_probe_plan"] = auth_plan.to_dict()
        record.metadata["authentication_mode"] = auth_mode
        record.metadata["authentication_mode_policy_version"] = (
            AUTHENTICATION_MODE_POLICY_VERSION
        )

        # Noninteractive contract — never from live prompt.
        ni_assessment = assess_noninteractive_contract(
            profile,
            discovery_installed=discovery.status is DiscoveryStatus.INSTALLED,
            help_text=help_summary,
            synthetic_verified=bool(overrides.get("capabilities_verified"))
            or bool(overrides.get("synthetic_noninteractive_verified")),
            force_editor_cli=overrides.get("force_editor_cli"),
        )
        record.noninteractive_status = ni_assessment.overall_status
        record.noninteractive_evidence = ni_assessment.overall_evidence
        record.noninteractive_contract = ni_assessment.to_dict()
        events.append(
            AuditEvent(
                event_type=AuditEventType.NONINTERACTIVE_CONTRACT_ASSESSED.value,
                message=ni_assessment.overall_evidence,
                provider_id=provider_id,
                details={
                    "overall_status": ni_assessment.overall_status,
                    "editor_cli_detected": ni_assessment.editor_cli_detected,
                    "synthetic_verified": ni_assessment.synthetic_verified,
                },
            )
        )

        if overrides.get("noninteractive_status"):
            record.noninteractive_status = overrides["noninteractive_status"]
            record.noninteractive_evidence = overrides.get(
                "noninteractive_evidence", record.noninteractive_evidence
            )

        # Capability assessments from contract dimensions.
        dim_map = {d.name: d for d in ni_assessment.dimensions}
        record.working_directory_binding_status = (
            dim_map["working_directory_binding"].status
            if "working_directory_binding" in dim_map
            else CapabilityStatus.UNAVAILABLE.value
        )
        record.isolated_worktree_compatibility = record.working_directory_binding_status
        record.structured_output_status = (
            dim_map["structured_output"].status
            if "structured_output" in dim_map
            else CapabilityStatus.UNAVAILABLE.value
        )
        record.timeout_support = (
            dim_map["timeout"].status
            if "timeout" in dim_map
            else CapabilityStatus.SUPPORTED_VERIFIED.value
        )
        record.cancellation_support = (
            dim_map["cancellation"].status
            if "cancellation" in dim_map
            else CapabilityStatus.SUPPORTED_DOCUMENTED.value
        )
        record.output_bounding_support = (
            dim_map["output_limits"].status
            if "output_limits" in dim_map
            else CapabilityStatus.SUPPORTED_VERIFIED.value
        )
        record.environment_sanitization_support = CapabilityStatus.SUPPORTED_VERIFIED.value
        record.network_behavior_classification = profile.network_behavior

        matrix = build_role_matrix(
            profile,
            authentication_status=record.authentication_status,
            noninteractive_status=record.noninteractive_status,
            provider_mode=mode.value,
            discovery_installed=discovery.status is DiscoveryStatus.INSTALLED,
        )
        record.role_matrix = [m.to_dict() for m in matrix]
        record.implementer_eligibility = role_eligibility(matrix, "implementer")
        record.reviewer_eligibility = role_eligibility(matrix, "reviewer")

        verdict, blockers, warnings = decide_provider_verdict(
            discovery_status=record.discovery_status,
            compatibility_status=record.compatibility_status,
            authentication_status=record.authentication_status,
            noninteractive_status=record.noninteractive_status,
            implementer_eligibility=record.implementer_eligibility,
            reviewer_eligibility=record.reviewer_eligibility,
            live_policy_status=record.live_policy_status,
            provider_mode=mode.value,
            provider_id=provider_id,
            allow_unknown_auth_conditional=allow_unknown_auth_conditional,
            authentication_mode=record.authentication_mode,
        )
        if profile.notes:
            warnings.append(profile.notes)
        record.final_readiness_verdict = verdict
        record.blockers = blockers
        record.warnings = warnings
        record.recommended_smoke_test_restrictions = [
            "no_live_invocation_until_separate_4d2_authorization",
            "no_auto_merge_deploy_release",
            "bound_to_registered_project_and_approved_plan",
            "timeout_and_output_limits_required",
        ]
        if record.implementer_eligibility in ("eligible", "conditionally_eligible"):
            record.recommended_round_4d2_role = "implementer"
        elif record.reviewer_eligibility in ("eligible", "conditionally_eligible"):
            record.recommended_round_4d2_role = "reviewer"
        else:
            record.recommended_round_4d2_role = None

        events.append(
            AuditEvent(
                event_type=AuditEventType.READINESS_DECISION_PRODUCED.value,
                message=f"Verdict: {verdict}",
                provider_id=provider_id,
                details={"blockers": blockers},
            )
        )
        record.audit_events = [e.to_dict() for e in events]
        record.live_provider_invocations = self._live_invocations
        assert record.live_provider_invocations == 0
        record.source_fingerprints = {
            "provider_config": fingerprint(config.sanitized_public_dict()),
            "project_registration": fingerprint(
                {"id": project.id, "root_path": project.root_path}
            ),
            "readiness_policy": READINESS_POLICY_VERSION,
            "adapter_version": adapter_version,
            "auth_probe_plan": fingerprint(auth_plan.to_dict()),
            "noninteractive_contract": fingerprint(record.noninteractive_contract),
        }
        record.evidence_references = [
            f"probe:{p.get('kind')}" for p in probes_out if not p.get("skipped")
        ]
        record.record_fingerprint = record.compute_fingerprint()
        return record

    def audit_all(
        self,
        *,
        project_id: str,
        providers: Sequence[str] | None = None,
        include_help_summary: bool = False,
        path_env: str | None = None,
        allow_unknown_auth_conditional: bool = False,
        enable_where: bool = True,
        enable_get_command: bool = True,
        probe_timeout: float | None = None,
        provider_overrides: dict[str, dict[str, Any]] | None = None,
        verify_noninteractive_contract: bool = False,
    ) -> ReadinessAuditBundle:
        ids = list(providers) if providers else [
            p for p in list_provider_ids() if p != "simulated"
        ]
        # Always include simulated note if auditing default set? Spec says audit registered adapters.
        # Include all registered except we skip simulated for live eligibility but can list it.
        if providers is None:
            ids = [p for p in list_provider_ids()]

        records: list[ProviderReadinessRecord] = []
        overrides_map = provider_overrides or {}
        for pid in ids:
            ovr = dict(overrides_map.get(pid) or {})
            if verify_noninteractive_contract and "synthetic_noninteractive_verified" not in ovr:
                # Flag requests contract assessment (already default); do not invent live proof.
                ovr.setdefault("verify_noninteractive_contract", True)
            rec = self.audit_provider(
                pid,
                project_id=project_id,
                include_help_summary=include_help_summary or verify_noninteractive_contract,
                path_env=path_env,
                allow_unknown_auth_conditional=allow_unknown_auth_conditional,
                enable_where=enable_where,
                enable_get_command=enable_get_command,
                probe_timeout=probe_timeout,
                synthetic_overrides=ovr or None,
            )
            records.append(rec)

        summaries = [
            {
                "provider_id": r.provider_id,
                "implementer_eligibility": r.implementer_eligibility,
                "reviewer_eligibility": r.reviewer_eligibility,
                "final_readiness_verdict": r.final_readiness_verdict,
            }
            for r in records
        ]
        independence, combinations = compute_independence(summaries)
        for r in records:
            r.reviewer_independence_status = independence

        agg = aggregate_verdict([r.final_readiness_verdict for r in records])
        host_verdict = compute_host_system_verdict(
            records,
            independence_status=independence,
            combinations=combinations,
        )
        recommended = next((c for c in combinations if c.recommended), None)
        blockers: list[str] = []
        warnings: list[str] = []
        for r in records:
            blockers.extend(f"{r.provider_id}:{b}" for b in r.blockers)
            warnings.extend(f"{r.provider_id}:{w}" for w in r.warnings)

        config = self._load_config()
        bundle = ReadinessAuditBundle(
            audit_id=new_audit_id(),
            schema_version=READINESS_SCHEMA_VERSION,
            readiness_policy_version=READINESS_POLICY_VERSION,
            generated_at=utc_now_iso(),
            project_id=project_id,
            repository_identity=_repository_identity(self.repo_root),
            repository_commit=_git_head(self.repo_root),
            host_platform=platform.system().lower(),
            provider_records=records,
            combinations=combinations,
            aggregate_verdict=agg,
            recommended_combination=recommended,
            blockers=blockers,
            warnings=warnings,
            live_provider_invocations=0,
            host_system_verdict=host_verdict,
            audit_events=[
                AuditEvent(
                    event_type=AuditEventType.LIVE_INVOCATION_BLOCKED.value,
                    message="Audit complete; live_provider_invocations=0",
                ),
                AuditEvent(
                    event_type=AuditEventType.HOST_SYSTEM_VERDICT_PRODUCED.value,
                    message=f"Host system verdict: {host_verdict}",
                    details={"host_system_verdict": host_verdict},
                ),
            ],
            source_fingerprints={
                "provider_config": fingerprint(config.sanitized_public_dict()),
                "readiness_policy": READINESS_POLICY_VERSION,
            },
        )
        bundle.record_fingerprint = bundle.compute_fingerprint()
        return bundle
