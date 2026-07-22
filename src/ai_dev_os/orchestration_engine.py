"""Bounded orchestration engine: impl → test → review → repair with stalemate detection."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .context_builder import build_context_packet
from .execution_audit import ExecutionAuditStore
from .fingerprints import fingerprint, fingerprint_context_manifest, fingerprint_plan, fingerprint_task
from .models import RepairRound, TaskStatus, utc_now_iso
from .orchestration_bindings import BindingError, validate_bindings
from .orchestration_config import OrchestrationConfig, load_orchestration_config
from .orchestration_models import (
    AUTOMATION_ORCH_SIMULATED,
    ORCHESTRATION_SCHEMA_VERSION,
    CompletionSummary,
    OrchestrationEvent,
    OrchestrationFailureClass,
    OrchestrationRecord,
    OrchestrationState,
    ProgressStatus,
    RoundEvidence,
    StalemateStatus,
    StructuredFinding,
    TERMINAL_ORCH_STATES,
    TestStatus,
    findings_fingerprint,
    next_allowed_orch_action,
)
from .orchestration_mutations import apply_fixture_mutation, worktree_content_fingerprint
from .orchestration_stalemate import (
    compute_progress_state_fingerprint,
    detect_stalemate,
    evaluate_round_progress,
)
from .orchestration_store import OrchestrationStore, OrchestrationStoreError
from .plan_store import PlanStore
from .project_registry import ProjectRegistry
from .provider_audit import ProviderAuditStore
from .provider_config import ProviderConfig, load_provider_config
from .provider_models import (
    FailureClass,
    ProviderMode,
    ProviderResultStatus,
    SimulatedFixture,
)
from .provider_runner import ProviderRunner
from .repair_rounds import RepairRoundStore
from .session_exec import run_session_tests
from .session_store import SessionStore
from .task_store import TaskStore
from .validation import ValidationError, apply_status_transition
from .worktrees import read_head


class OrchestrationError(ValidationError):
    def __init__(
        self,
        message: str,
        failure_class: OrchestrationFailureClass = OrchestrationFailureClass.POLICY_REJECTED,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class


# Built-in calculator-demo scenarios (fixture + harness mutation scripts).
SCENARIO_SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "direct_success": [
        {"phase": "implementation", "fixture": SimulatedFixture.SUCCESS_IMPL.value, "mutation": "add_subtract"},
        {"phase": "review", "fixture": SimulatedFixture.SUCCESS_REVIEW.value},
    ],
    "pass_with_notes": [
        {"phase": "implementation", "fixture": SimulatedFixture.SUCCESS_IMPL.value, "mutation": "add_subtract"},
        {"phase": "review", "fixture": SimulatedFixture.SUCCESS_REVIEW_WITH_NOTES.value},
    ],
    "one_repair": [
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "add_subtract",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value},
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "cosmetic_only",
        },
        {"phase": "review", "fixture": SimulatedFixture.SUCCESS_REVIEW.value},
    ],
    "test_fail_then_repair": [
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "add_subtract_buggy",
        },
        # tests fail → repair; skip review until tests pass
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "add_subtract_fixed",
        },
        {"phase": "review", "fixture": SimulatedFixture.SUCCESS_REVIEW.value},
    ],
    "stalemate_identical": [
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "add_subtract",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_IDENTICAL.value},
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "cosmetic_only",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_IDENTICAL.value},
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "cosmetic_only",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_IDENTICAL.value},
    ],
    "stalemate_oscillation": [
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "oscillation_a",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value},
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "oscillation_b",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value},
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "oscillation_a",
        },
        {"phase": "review", "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value},
    ],
    "repair_limit": [
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "add_subtract",
        },
        {
            "phase": "review",
            "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value,
            "findings": [
                {
                    "finding_id": "def-1",
                    "severity": "major",
                    "summary": "issue 1",
                    "path": "calculator/ops.py",
                    "code": "L1",
                }
            ],
        },
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "cosmetic_only",
        },
        {
            "phase": "review",
            "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value,
            "findings": [
                {
                    "finding_id": "def-2",
                    "severity": "major",
                    "summary": "issue 2",
                    "path": "calculator/ops.py",
                    "code": "L2",
                }
            ],
        },
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "add_subtract",
        },
        {
            "phase": "review",
            "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value,
            "findings": [
                {
                    "finding_id": "def-3",
                    "severity": "major",
                    "summary": "issue 3",
                    "path": "calculator/ops.py",
                    "code": "L3",
                }
            ],
        },
        {
            "phase": "implementation",
            "fixture": SimulatedFixture.SUCCESS_IMPL.value,
            "mutation": "cosmetic_only",
        },
        {
            "phase": "review",
            "fixture": SimulatedFixture.CHANGES_REQUIRED_REVIEW.value,
            "findings": [
                {
                    "finding_id": "def-4",
                    "severity": "major",
                    "summary": "issue 4",
                    "path": "calculator/ops.py",
                    "code": "L4",
                }
            ],
        },
    ],
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class OrchestrationEngine:
    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        registry: ProjectRegistry | None = None,
        orch_config: OrchestrationConfig | None = None,
        provider_config: ProviderConfig | None = None,
        task_store: TaskStore | None = None,
        plan_store: PlanStore | None = None,
        session_store: SessionStore | None = None,
        orch_store: OrchestrationStore | None = None,
        provider_runner: ProviderRunner | None = None,
        repair_store: RepairRoundStore | None = None,
        execution_audit: ExecutionAuditStore | None = None,
    ) -> None:
        self.workspace_root = workspace_root or (_repo_root() / "workspace")
        self.registry = registry or ProjectRegistry()
        self.orch_config = orch_config or load_orchestration_config()
        self.provider_config = provider_config or load_provider_config()
        self.task_store = task_store or TaskStore()
        self.plan_store = plan_store or PlanStore()
        self.session_store = session_store or SessionStore(
            workspace_root=self.workspace_root, registry=self.registry
        )
        self.orch_store = orch_store or OrchestrationStore(workspace_root=self.workspace_root)
        self.repair_store = repair_store or RepairRoundStore(workspace_root=self.workspace_root)
        self.execution_audit = execution_audit or ExecutionAuditStore(
            workspace_root=self.workspace_root
        )
        self.provider_runner = provider_runner or ProviderRunner(
            workspace_root=self.workspace_root,
            registry=self.registry,
            config=self.provider_config,
            task_store=self.task_store,
            plan_store=self.plan_store,
            session_store=self.session_store,
            audit_store=ProviderAuditStore(workspace_root=self.workspace_root),
        )
        self._active_round: RoundEvidence | None = None

    # ------------------------------------------------------------------ create
    def create(
        self,
        *,
        task_id: str,
        plan_id: str,
        session_id: str,
        scenario_id: str | None = None,
        fixture_script: list[dict[str, Any]] | None = None,
        orchestration_id: str | None = None,
        test_paths: list[str] | None = None,
    ) -> OrchestrationRecord:
        task = self.task_store.load(task_id)
        plan = self.plan_store.load(plan_id)
        session = self.session_store.load(session_id)
        project = self.registry.require(task.project_id)

        if task.status is not TaskStatus.APPROVED_FOR_IMPLEMENTATION and task.status not in (
            TaskStatus.IMPLEMENTING,
            TaskStatus.REVIEW_FAILED,
        ):
            raise OrchestrationError(
                f"Task must be approved_for_implementation (got {task.status.value})"
            )

        oid = orchestration_id or f"orch-{uuid.uuid4().hex[:12]}"
        if self.orch_store.exists(oid):
            raise OrchestrationError(f"Orchestration already exists: {oid}")

        script = list(fixture_script or [])
        if scenario_id:
            if scenario_id not in SCENARIO_SCRIPTS:
                raise OrchestrationError(f"Unknown scenario_id: {scenario_id}")
            script = list(SCENARIO_SCRIPTS[scenario_id])

        worktree = Path(session.worktree_path).resolve()
        head = read_head(worktree)
        packet = build_context_packet(task, project.root_path)
        impl_ctx = fingerprint_context_manifest(packet.manifest)
        approved_fp = plan.approved_fingerprint or fingerprint_plan(plan.to_dict())

        record = OrchestrationRecord(
            schema_version=ORCHESTRATION_SCHEMA_VERSION,
            orchestration_id=oid,
            orchestration_policy_version=self.orch_config.policy_version,
            task_id=task.id,
            task_fingerprint=fingerprint_task(task.to_dict()),
            plan_id=plan.plan_id,
            approved_plan_fingerprint=str(approved_fp),
            approval_record_id=plan.approved_by,
            project_id=task.project_id,
            session_id=session.session_id,
            worktree_id=str(worktree),
            registered_project_root_identity=str(Path(project.root_path).resolve()),
            starting_commit=session.starting_commit,
            current_worktree_commit=head,
            implementation_role=self.orch_config.implementation_role,
            review_role=self.orch_config.review_role,
            implementation_provider_id=self.orch_config.implementation_provider_id,
            review_provider_id=self.orch_config.review_provider_id,
            invocation_mode=self.orch_config.default_invocation_mode,
            implementation_context_fingerprint=impl_ctx,
            current_state=OrchestrationState.CREATED.value,
            maximum_step_count=self.orch_config.max_total_steps,
            maximum_repair_rounds=self.orch_config.max_repair_rounds,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            automation_status=AUTOMATION_ORCH_SIMULATED,
            scenario_id=scenario_id,
            fixture_script=script,
            test_paths=list(test_paths or ["tests"]),
        )

        try:
            validate_bindings(
                record,
                task=task,
                plan=plan,
                registry=self.registry,
                session_store=self.session_store,
                require_clean_for_create=False,
            )
        except BindingError as exc:
            raise OrchestrationError(str(exc), exc.failure_class) from exc

        self.orch_store.save_record(record)
        return record

    def validate(self, orchestration_id: str) -> dict[str, Any]:
        record = self.orch_store.load_record(orchestration_id)
        task = self.task_store.load(record.task_id)
        plan = self.plan_store.load(record.plan_id)
        try:
            validate_bindings(
                record,
                task=task,
                plan=plan,
                registry=self.registry,
                session_store=self.session_store,
            )
            return {
                "valid": True,
                "orchestration_id": orchestration_id,
                "state": record.current_state,
                "errors": [],
            }
        except BindingError as exc:
            return {
                "valid": False,
                "orchestration_id": orchestration_id,
                "state": record.current_state,
                "errors": [str(exc)],
                "failure_class": exc.failure_class.value,
            }

    def preview(self, orchestration_id: str) -> dict[str, Any]:
        record = self.orch_store.load_record(orchestration_id)
        state = record.state()
        return {
            "orchestration_id": orchestration_id,
            "current_state": record.current_state,
            "next_allowed_action": next_allowed_orch_action(state),
            "current_step_number": record.current_step_number,
            "current_repair_round": record.current_repair_round,
            "fixture_index": record.fixture_index,
            "next_fixture": (
                record.fixture_script[record.fixture_index]
                if record.fixture_index < len(record.fixture_script)
                else None
            ),
            "stalemate_status": record.stalemate_status,
            "test_status": record.test_status,
            "review_verdict": record.review_verdict,
            "stop_reason": record.stop_reason,
            "mutates": False,
        }

    def status(self, orchestration_id: str) -> dict[str, Any]:
        record = self.orch_store.load_record(orchestration_id)
        return {
            "orchestration_id": record.orchestration_id,
            "task_id": record.task_id,
            "plan_id": record.plan_id,
            "project_id": record.project_id,
            "session_id": record.session_id,
            "current_state": record.current_state,
            "current_step_number": record.current_step_number,
            "current_repair_round": record.current_repair_round,
            "current_round_number": record.current_round_number,
            "test_status": record.test_status,
            "review_verdict": record.review_verdict,
            "progress_status": record.progress_status,
            "stalemate_status": record.stalemate_status,
            "stop_reason": record.stop_reason,
            "human_action_requirement": record.human_action_requirement,
            "next_allowed_action": next_allowed_orch_action(record.state()),
            "automation_status": record.automation_status,
            "scenario_id": record.scenario_id,
            "last_failure_class": record.last_failure_class,
        }

    def history(self, orchestration_id: str) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.orch_store.load_events(orchestration_id)]

    def stalemate_evidence(self, orchestration_id: str) -> dict[str, Any]:
        record = self.orch_store.load_record(orchestration_id)
        rounds = self.orch_store.load_rounds(orchestration_id)
        return {
            "orchestration_id": orchestration_id,
            "stalemate_status": record.stalemate_status,
            "consecutive_no_progress": record.consecutive_no_progress,
            "consecutive_malformed": record.consecutive_malformed,
            "progress_fingerprint_history": list(record.progress_fingerprint_history),
            "rounds": [
                {
                    "round_number": r.round_number,
                    "progress_state_fingerprint": r.progress_state_fingerprint,
                    "review_verdict": r.review_verdict,
                    "failing_test_fingerprint": r.failing_test_fingerprint,
                    "review_findings_fingerprint": r.review_findings_fingerprint,
                    "worktree_diff_fingerprint": r.worktree_diff_fingerprint,
                    "stalemate_evidence": r.stalemate_evidence,
                    "no_progress_reason": r.no_progress_reason,
                }
                for r in rounds
            ],
            "stop_reason": record.stop_reason,
        }

    def cancel(self, orchestration_id: str, reason: str = "operator cancel") -> OrchestrationRecord:
        record = self.orch_store.load_record(orchestration_id)
        if record.is_terminal():
            if record.state() is OrchestrationState.CANCELLED:
                return record
            raise OrchestrationError(
                f"Cannot cancel terminal orchestration in state {record.current_state}"
            )
        record = self._transition(
            record,
            OrchestrationState.CANCELLED,
            notes=reason,
            failure_class=OrchestrationFailureClass.ORCHESTRATION_CANCELLED,
        )
        record.cancelled_at = utc_now_iso()
        record.stop_reason = reason
        record.human_action_requirement = "create new orchestration if work should continue"
        self.orch_store.save_record(record)
        self._write_summary(record)
        return record

    def resume(self, orchestration_id: str) -> OrchestrationRecord:
        record = self.orch_store.load_record(orchestration_id)
        if record.state() is OrchestrationState.CANCELLED:
            raise OrchestrationError(
                "Cancelled orchestration cannot resume; create a new orchestration",
                OrchestrationFailureClass.ORCHESTRATION_CANCELLED,
            )
        if record.is_terminal():
            raise OrchestrationError(
                f"Terminal orchestration cannot resume ({record.current_state})"
            )
        task = self.task_store.load(record.task_id)
        plan = self.plan_store.load(record.plan_id)
        try:
            validate_bindings(
                record,
                task=task,
                plan=plan,
                registry=self.registry,
                session_store=self.session_store,
            )
        except BindingError as exc:
            raise OrchestrationError(str(exc), exc.failure_class) from exc
        return record

    def run_until_boundary(self, orchestration_id: str, *, max_steps: int | None = None) -> OrchestrationRecord:
        limit = max_steps if max_steps is not None else self.orch_config.max_total_steps
        record = self.orch_store.load_record(orchestration_id)
        steps = 0
        while not record.is_terminal() and steps < limit:
            if record.current_step_number >= record.maximum_step_count:
                record = self._stop_step_limit(record)
                break
            record = self.step(orchestration_id)
            steps += 1
            if record.state() is OrchestrationState.REPAIR_REQUIRED:
                # Boundary: operator can inspect before opening repair, but auto-continue
                # within run_until_boundary by opening repair if eligible.
                record = self.step(orchestration_id)
                steps += 1
        return self.orch_store.load_record(orchestration_id)

    # ------------------------------------------------------------------- step
    def step(self, orchestration_id: str) -> OrchestrationRecord:
        record = self.orch_store.load_record(orchestration_id)
        if record.state() is OrchestrationState.CANCELLED:
            raise OrchestrationError(
                "Cannot step cancelled orchestration",
                OrchestrationFailureClass.ORCHESTRATION_CANCELLED,
            )
        if record.is_terminal():
            raise OrchestrationError(f"Terminal state: {record.current_state}")

        if record.current_step_number >= record.maximum_step_count:
            return self._stop_step_limit(record)

        task = self.task_store.load(record.task_id)
        plan = self.plan_store.load(record.plan_id)
        try:
            validate_bindings(
                record,
                task=task,
                plan=plan,
                registry=self.registry,
                session_store=self.session_store,
            )
        except BindingError as exc:
            return self._block(record, str(exc), exc.failure_class)

        state = record.state()
        if state is OrchestrationState.CREATED:
            return self._transition(record, OrchestrationState.READY, notes="bindings validated")
        if state is OrchestrationState.READY:
            self._ensure_task_implementing(task)
            return self._transition(
                record, OrchestrationState.IMPLEMENTATION_PENDING, notes="ready for implementation"
            )
        if state is OrchestrationState.IMPLEMENTATION_PENDING:
            self._restore_active_round(record)
            return self._run_implementation(record)
        if state is OrchestrationState.IMPLEMENTATION_RUNNING:
            # Should not linger; treat as finish validation
            return self._transition(
                record,
                OrchestrationState.IMPLEMENTATION_RESULT_PENDING_VALIDATION,
                notes="implementation finished",
            )
        if state is OrchestrationState.IMPLEMENTATION_RESULT_PENDING_VALIDATION:
            self._restore_active_round(record)
            return self._validate_implementation_result(record)
        if state is OrchestrationState.TESTING_PENDING:
            self._restore_active_round(record)
            return self._run_tests(record)
        if state is OrchestrationState.TESTING_RUNNING:
            return self._transition(record, OrchestrationState.REVIEW_PENDING, notes="tests finished")
        if state is OrchestrationState.REVIEW_PENDING:
            self._restore_active_round(record)
            return self._run_review(record)
        if state is OrchestrationState.REVIEW_RUNNING:
            self._restore_active_round(record)
            return self._finish_review(record)
        if state is OrchestrationState.REPAIR_REQUIRED:
            return self._open_repair(record)
        if state is OrchestrationState.REPAIR_PENDING:
            return self._transition(
                record,
                OrchestrationState.IMPLEMENTATION_PENDING,
                notes="repair pending → implementation",
            )
        raise OrchestrationError(f"No step handler for state {state.value}")

    # ------------------------------------------------------------- transitions
    def _transition(
        self,
        record: OrchestrationRecord,
        to_state: OrchestrationState,
        *,
        notes: str = "",
        failure_class: OrchestrationFailureClass = OrchestrationFailureClass.NONE,
        refs: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> OrchestrationRecord:
        from_state = record.state()
        allowed = ORCH_TRANSITIONS_SAFE(from_state)
        if to_state not in allowed:
            raise OrchestrationError(
                f"Prohibited transition {from_state.value} → {to_state.value}"
            )
        eid = event_id or f"evt-{uuid.uuid4().hex[:12]}"
        # Idempotent: if latest event already this transition, return
        events = self.orch_store.load_events(record.orchestration_id)
        if events and events[-1].event_id == eid:
            return record

        record.current_step_number += 1
        event = OrchestrationEvent(
            event_id=eid,
            orchestration_id=record.orchestration_id,
            from_state=from_state.value,
            to_state=to_state.value,
            step_number=record.current_step_number,
            failure_class=failure_class.value,
            notes=notes,
            refs=refs or {},
            created_at=utc_now_iso(),
        )
        self.orch_store.append_event(event)
        record.current_state = to_state.value
        record.latest_event_id = eid
        record.last_failure_class = failure_class.value
        if to_state is OrchestrationState.COMPLETED:
            record.completed_at = utc_now_iso()
        record.updated_at = utc_now_iso()
        self.orch_store.save_record(record)
        return record

    def _block(
        self,
        record: OrchestrationRecord,
        reason: str,
        failure_class: OrchestrationFailureClass,
        *,
        state: OrchestrationState | None = None,
    ) -> OrchestrationRecord:
        target = state or OrchestrationState.BLOCKED
        # Force-allow from any non-terminal via explicit path
        if record.is_terminal():
            return record
        from_state = record.state()
        if target not in ORCH_TRANSITIONS_SAFE(from_state):
            # Use cancelled-like escape: only if blocked/human_review allowed
            if OrchestrationState.BLOCKED in ORCH_TRANSITIONS_SAFE(from_state):
                target = OrchestrationState.BLOCKED
            elif OrchestrationState.HUMAN_REVIEW_REQUIRED in ORCH_TRANSITIONS_SAFE(from_state):
                target = OrchestrationState.HUMAN_REVIEW_REQUIRED
            else:
                raise OrchestrationError(f"Cannot block from {from_state.value}: {reason}")
        record.stop_reason = reason
        record.human_action_requirement = "human review required"
        record = self._transition(
            record, target, notes=reason, failure_class=failure_class
        )
        self._write_summary(record)
        return record

    def _stop_step_limit(self, record: OrchestrationRecord) -> OrchestrationRecord:
        target = OrchestrationState(self.orch_config.step_limit_state)
        return self._block(
            record,
            "Maximum orchestration step count reached",
            OrchestrationFailureClass.STEP_LIMIT_REACHED,
            state=target if target in TERMINAL_ORCH_STATES else OrchestrationState.BLOCKED,
        )

    def _write_summary(self, record: OrchestrationRecord) -> None:
        summary = CompletionSummary(
            orchestration_id=record.orchestration_id,
            final_state=record.current_state,
            repair_rounds_used=record.current_repair_round,
            steps_used=record.current_step_number,
            review_verdict=record.review_verdict,
            test_status=record.test_status,
            stalemate_status=record.stalemate_status,
            stop_reason=record.stop_reason,
            progress_status=record.progress_status,
            human_action_requirement=record.human_action_requirement,
            automation_status=record.automation_status,
            created_at=utc_now_iso(),
        )
        self.orch_store.save_summary(summary)

    def _ensure_task_implementing(self, task) -> None:
        if task.status is TaskStatus.APPROVED_FOR_IMPLEMENTATION:
            task = apply_status_transition(task, TaskStatus.IMPLEMENTING)
            self.task_store.update(task)
        elif task.status is TaskStatus.REVIEW_FAILED:
            task = apply_status_transition(task, TaskStatus.IMPLEMENTING)
            self.task_store.update(task)

    def _restore_active_round(self, record: OrchestrationRecord) -> None:
        if self._active_round and not self._active_round.finished_at:
            return
        rounds = self.orch_store.load_rounds(record.orchestration_id)
        if rounds and not rounds[-1].finished_at:
            self._active_round = rounds[-1]
        elif rounds and record.current_round_number == rounds[-1].round_number:
            self._active_round = rounds[-1]

    def _next_script_entry(self, record: OrchestrationRecord, phase: str) -> dict[str, Any]:
        while record.fixture_index < len(record.fixture_script):
            entry = record.fixture_script[record.fixture_index]
            if entry.get("phase") == phase:
                return entry
            # Skip mismatched phases carefully — for test_fail scenario review comes later
            if phase == "implementation" and entry.get("phase") == "review":
                break
            if phase == "review" and entry.get("phase") == "implementation":
                break
            record.fixture_index += 1
        # Default fixtures
        if phase == "implementation":
            return {"phase": "implementation", "fixture": SimulatedFixture.SUCCESS_IMPL.value, "mutation": "noop"}
        return {"phase": "review", "fixture": SimulatedFixture.SUCCESS_REVIEW.value}

    def _consume_script_entry(self, record: OrchestrationRecord, entry: dict[str, Any]) -> None:
        if record.fixture_index < len(record.fixture_script):
            cur = record.fixture_script[record.fixture_index]
            if cur == entry or (
                cur.get("phase") == entry.get("phase")
                and cur.get("fixture") == entry.get("fixture")
            ):
                record.fixture_index += 1

    # ------------------------------------------------------- implementation
    def _run_implementation(self, record: OrchestrationRecord) -> OrchestrationRecord:
        record = self._transition(
            record, OrchestrationState.IMPLEMENTATION_RUNNING, notes="start implementation"
        )
        entry = self._next_script_entry(record, "implementation")
        fixture = entry.get("fixture") or SimulatedFixture.SUCCESS_IMPL.value
        mutation = entry.get("mutation")

        if not self._active_round or self._active_round.finished_at:
            record.current_round_number += 1
            self._active_round = RoundEvidence(
                orchestration_id=record.orchestration_id,
                round_number=record.current_round_number,
                repair_round_number=record.current_repair_round,
                started_at=utc_now_iso(),
                pre_implementation_commit=record.current_worktree_commit,
                implementation_context_fingerprint=record.implementation_context_fingerprint,
            )

        session = self.session_store.load(record.session_id)
        worktree = Path(session.worktree_path)

        # Harness mutation BEFORE provider result (provider text never applied).
        mut_result = None
        if mutation:
            mut_result = apply_fixture_mutation(worktree, mutation)
            record.current_worktree_commit = mut_result["commit"] or record.current_worktree_commit
            self._active_round.files_changed = list(mut_result["files_changed"])
            self._active_round.worktree_diff_fingerprint = mut_result["diff_fingerprint"]
            self._active_round.post_implementation_commit = mut_result["commit"]

        req = self.provider_runner.build_request(
            provider_id=record.implementation_provider_id,
            task_id=record.task_id,
            plan_id=record.plan_id,
            session_id=record.session_id,
            role=record.implementation_role,
            invocation_mode=ProviderMode.SIMULATED,
            fixture_id=fixture,
            timeout_seconds=self.orch_config.default_timeout_seconds,
            output_limit_bytes=self.orch_config.default_output_limit_bytes,
        )
        # Lock context fingerprint from orchestration record
        req.context_or_handoff_fingerprint = (
            record.implementation_context_fingerprint or req.context_or_handoff_fingerprint
        )
        # Distinct attempt key so repair rounds are not treated as duplicate requests.
        meta = dict(req.metadata or {})
        meta["attempt_key"] = (
            f"impl:{record.orchestration_id}:{record.current_round_number}:"
            f"{record.current_repair_round}:{record.fixture_index}"
        )
        req.metadata = meta
        # Restore impl context on task for policy binding
        task = self.task_store.load(record.task_id)
        tmeta = dict(task.metadata or {})
        tmeta["context_or_handoff_fingerprint"] = req.context_or_handoff_fingerprint
        task.metadata = tmeta
        self.task_store.update(task)
        self.provider_runner.audit_store.save_request(req)

        if req.request_id in record.consumed_request_ids:
            return self._block(
                record,
                "Duplicate implementation request ID",
                OrchestrationFailureClass.DUPLICATE_REQUEST,
            )

        result = self.provider_runner.run_simulated(req, fixture_id=fixture)
        record.consumed_request_ids.append(req.request_id)
        self._active_round.implementation_request_id = req.request_id
        self._active_round.implementation_result_id = req.request_id
        self._active_round.implementation_result_fingerprint = result.result_fingerprint
        self._active_round.implementation_status = result.provider_result_status.value

        self._consume_script_entry(record, entry)
        record = self._transition(
            record,
            OrchestrationState.IMPLEMENTATION_RESULT_PENDING_VALIDATION,
            notes=f"implementation fixture={fixture}",
            refs={"request_id": req.request_id, "status": result.provider_result_status.value},
        )
        # Persist intermediate round
        self.orch_store.save_round(self._active_round)
        self.orch_store.save_record(record)

        # Map provider failures
        if result.provider_result_status is ProviderResultStatus.TIMEOUT:
            record.consecutive_malformed = 0
            return self._block(
                record, "Provider timeout", OrchestrationFailureClass.PROVIDER_TIMEOUT
            )
        if result.provider_result_status is ProviderResultStatus.CANCELLED:
            return self._block(
                record, "Provider cancelled", OrchestrationFailureClass.PROVIDER_CANCELLED
            )
        if result.provider_result_status is ProviderResultStatus.DUPLICATE:
            return self._block(
                record, "Duplicate provider request", OrchestrationFailureClass.DUPLICATE_REQUEST
            )
        if result.failure_class is FailureClass.MALFORMED_OUTPUT:
            record.consecutive_malformed += 1
            self.orch_store.save_record(record)
            decision = detect_stalemate(
                self.orch_store.load_rounds(record.orchestration_id),
                history=record.progress_fingerprint_history,
                consecutive_no_progress=record.consecutive_no_progress,
                consecutive_malformed=record.consecutive_malformed,
                config=self.orch_config,
            )
            if decision.stalemate:
                return self._stalemate_stop(record, decision.reason, decision.failure_class)
            return self._block(
                record,
                "Malformed implementation result",
                OrchestrationFailureClass.MALFORMED_PROVIDER_RESULT,
            )
        if result.provider_result_status is ProviderResultStatus.REJECTED:
            return self._block(
                record,
                result.rejection_reason or "Provider rejected",
                OrchestrationFailureClass.POLICY_REJECTED,
            )
        if result.provider_result_status is not ProviderResultStatus.SUCCESS:
            return self._block(
                record,
                result.rejection_reason or "Provider failed",
                OrchestrationFailureClass.PROVIDER_FAILED,
            )

        payload = result.normalized_payload or {}
        if payload.get("scope_change") or payload.get("reapproval_required"):
            return self._block(
                record,
                "Scope change detected; reapproval required",
                OrchestrationFailureClass.SCOPE_CHANGE_DETECTED,
            )

        if not mut_result:
            # Still fingerprint worktree content
            fp = worktree_content_fingerprint(worktree)
            self._active_round.worktree_diff_fingerprint = fp
            self._active_round.post_implementation_commit = read_head(worktree)

        return record

    def _validate_implementation_result(self, record: OrchestrationRecord) -> OrchestrationRecord:
        if not self._active_round or not self._active_round.implementation_result_id:
            return self._block(
                record,
                "Missing implementation result for validation",
                OrchestrationFailureClass.IMPLEMENTATION_RESULT_INVALID,
            )
        try:
            result = self.provider_runner.audit_store.load_result(
                self._active_round.implementation_result_id
            )
        except FileNotFoundError:
            return self._block(
                record,
                "Implementation result artifact missing",
                OrchestrationFailureClass.IMPLEMENTATION_RESULT_INVALID,
            )
        if result.provider_result_status is not ProviderResultStatus.SUCCESS:
            return self._block(
                record,
                "Implementation result not successful",
                OrchestrationFailureClass.IMPLEMENTATION_RESULT_INVALID,
            )
        return self._transition(
            record, OrchestrationState.TESTING_PENDING, notes="implementation validated"
        )

    # ----------------------------------------------------------------- tests
    def _run_tests(self, record: OrchestrationRecord) -> OrchestrationRecord:
        record = self._transition(
            record, OrchestrationState.TESTING_RUNNING, notes="start targeted tests"
        )
        env = run_session_tests(
            record.session_id,
            test_paths=record.test_paths,
            timeout=self.orch_config.default_timeout_seconds,
            output_limit_bytes=self.orch_config.default_output_limit_bytes,
            session_store=self.session_store,
            audit_store=self.execution_audit,
            extra_flags=["-q"],
        )
        if self._active_round:
            self._active_round.targeted_tests_requested = list(record.test_paths)
            self._active_round.targeted_tests_executed = list(env.tests_executed or record.test_paths)
            self._active_round.test_execution_result_id = env.execution_id
            self._active_round.test_result_fingerprint = fingerprint(
                {
                    "exit_code": env.exit_code,
                    "status": env.execution_status.value
                    if hasattr(env.execution_status, "value")
                    else str(env.execution_status),
                    "stdout_tail": (env.stdout or "")[-500:],
                }
            )
            failing: list[str] = []
            if env.exit_code not in (0, None) or (
                hasattr(env, "policy_decision")
                and str(getattr(env.policy_decision, "value", env.policy_decision)) == "deny"
            ):
                failing = ["tests"]
            # Parse simple failed node ids if present
            out = (env.stdout or "") + (env.stderr or "")
            for line in out.splitlines():
                if "FAILED" in line:
                    failing.append(line.strip()[:200])
            self._active_round.failing_test_identifiers = sorted(set(failing))
            self._active_round.failing_test_fingerprint = fingerprint(
                self._active_round.failing_test_identifiers
            )
            self._active_round.passing_test_count = (
                0 if failing else 1
            )
            self.orch_store.save_round(self._active_round)

        if env.exit_code is None and "reject" in (env.rejection_reason or "").lower():
            record.test_status = TestStatus.REJECTED.value
            return self._block(
                record,
                env.rejection_reason or "Test command rejected",
                OrchestrationFailureClass.TEST_COMMAND_REJECTED,
            )

        if env.exit_code != 0:
            record.test_status = TestStatus.FAILED.value
            self.orch_store.save_record(record)
            if self.orch_config.allow_test_failure_repair:
                return self._transition(
                    record,
                    OrchestrationState.REPAIR_REQUIRED,
                    notes="tests failed; repair eligible",
                    failure_class=OrchestrationFailureClass.TESTS_FAILED,
                )
            return self._block(
                record, "Tests failed", OrchestrationFailureClass.TESTS_FAILED
            )

        record.test_status = TestStatus.PASSED.value
        self.orch_store.save_record(record)
        # Move task toward review
        task = self.task_store.load(record.task_id)
        if task.status is TaskStatus.IMPLEMENTING:
            task = apply_status_transition(task, TaskStatus.VALIDATING)
            self.task_store.update(task)
            task = apply_status_transition(task, TaskStatus.READY_FOR_REVIEW)
            self.task_store.update(task)
        return self._transition(
            record, OrchestrationState.REVIEW_PENDING, notes="tests passed"
        )

    # ---------------------------------------------------------------- review
    def _build_review_context_fingerprint(self, record: OrchestrationRecord) -> str:
        rounds = self.orch_store.load_rounds(record.orchestration_id)
        payload = {
            "plan_id": record.plan_id,
            "approved_plan_fingerprint": record.approved_plan_fingerprint,
            "task_id": record.task_id,
            "implementation_result_id": (
                self._active_round.implementation_result_id if self._active_round else None
            ),
            "test_execution_result_id": (
                self._active_round.test_execution_result_id if self._active_round else None
            ),
            "test_status": record.test_status,
            "prior_findings": [
                f.to_dict()
                for r in rounds
                for f in r.canonical_findings
            ],
            "role": record.review_role,
        }
        return fingerprint(payload)

    def _run_review(self, record: OrchestrationRecord) -> OrchestrationRecord:
        record = self._transition(
            record, OrchestrationState.REVIEW_RUNNING, notes="start independent review"
        )
        review_ctx = self._build_review_context_fingerprint(record)
        record.review_context_fingerprint = review_ctx
        # Provider policy binds request context to task metadata; set review context explicitly.
        task = self.task_store.load(record.task_id)
        meta = dict(task.metadata or {})
        meta["context_or_handoff_fingerprint"] = review_ctx
        meta["review_context_fingerprint"] = review_ctx
        task.metadata = meta
        self.task_store.update(task)

        entry = self._next_script_entry(record, "review")
        fixture = entry.get("fixture") or SimulatedFixture.SUCCESS_REVIEW.value

        req = self.provider_runner.build_request(
            provider_id=record.review_provider_id,
            task_id=record.task_id,
            plan_id=record.plan_id,
            session_id=record.session_id,
            role=record.review_role,
            invocation_mode=ProviderMode.SIMULATED,
            fixture_id=fixture,
            timeout_seconds=self.orch_config.default_timeout_seconds,
            output_limit_bytes=self.orch_config.default_output_limit_bytes,
        )
        # build_request may refresh impl context — force independent review context.
        req.context_or_handoff_fingerprint = review_ctx
        meta = dict(req.metadata or {})
        meta["attempt_key"] = (
            f"review:{record.orchestration_id}:{record.current_round_number}:"
            f"{record.current_repair_round}:{record.fixture_index}"
        )
        req.metadata = meta
        task = self.task_store.load(record.task_id)
        meta = dict(task.metadata or {})
        meta["context_or_handoff_fingerprint"] = review_ctx
        task.metadata = meta
        self.task_store.update(task)
        self.provider_runner.audit_store.save_request(req)

        if req.request_id in record.consumed_request_ids:
            return self._block(
                record,
                "Duplicate review request ID",
                OrchestrationFailureClass.DUPLICATE_REQUEST,
            )

        result = self.provider_runner.run_simulated(req, fixture_id=fixture)
        record.consumed_request_ids.append(req.request_id)
        self._consume_script_entry(record, entry)

        if self._active_round:
            self._active_round.review_request_id = req.request_id
            self._active_round.review_result_id = req.request_id
            self._active_round.review_result_fingerprint = result.result_fingerprint
            self._active_round.review_context_fingerprint = review_ctx

        self.orch_store.save_record(record)

        if result.failure_class is FailureClass.MALFORMED_OUTPUT:
            record.consecutive_malformed += 1
            return self._block(
                record,
                "Malformed review result",
                OrchestrationFailureClass.REVIEW_RESULT_INVALID,
            )
        if result.provider_result_status is not ProviderResultStatus.SUCCESS:
            return self._block(
                record,
                result.rejection_reason or "Review provider failed",
                OrchestrationFailureClass.PROVIDER_FAILED,
            )

        payload = result.normalized_payload or {}
        # Script entry may override findings for deterministic repair-limit tests.
        entry_findings = entry.get("findings")
        if entry_findings is not None:
            findings_raw = entry_findings
            verdict = str(entry.get("verdict") or payload.get("verdict") or "")
        else:
            verdict = str(payload.get("verdict") or "")
            findings_raw = payload.get("findings") or []
        findings = [
            StructuredFinding(
                finding_id=str(f.get("finding_id") or f"f-{i}"),
                severity=str(f.get("severity") or "note"),
                summary=str(f.get("summary") or ""),
                path=f.get("path"),
                code=f.get("code"),
            )
            for i, f in enumerate(findings_raw)
            if isinstance(f, dict)
        ]
        if self._active_round:
            self._active_round.review_verdict = verdict
            self._active_round.canonical_findings = findings
            self._active_round.review_findings_fingerprint = findings_fingerprint(findings)
            if not self._active_round.worktree_diff_fingerprint:
                session = self.session_store.load(record.session_id)
                self._active_round.worktree_diff_fingerprint = worktree_content_fingerprint(
                    Path(session.worktree_path)
                )
            if not self._active_round.failing_test_fingerprint:
                self._active_round.failing_test_identifiers = []
                self._active_round.failing_test_fingerprint = fingerprint([])
            self._active_round.progress_state_fingerprint = compute_progress_state_fingerprint(
                self._active_round
            )
            self._active_round.finished_at = utc_now_iso()

        record.review_verdict = verdict
        self.orch_store.save_record(record)
        return self._finish_review(record)

    def _finish_review(self, record: OrchestrationRecord) -> OrchestrationRecord:
        verdict = record.review_verdict or ""
        rounds = self.orch_store.load_rounds(record.orchestration_id)
        current = self._active_round
        if current:
            # Ensure saved
            self.orch_store.save_round(current)
            rounds = self.orch_store.load_rounds(record.orchestration_id)

        previous = rounds[-2] if len(rounds) >= 2 else None
        if current:
            prog = evaluate_round_progress(current, previous)
            record.progress_status = prog.progress_status.value
            if prog.progress_status is ProgressStatus.NO_PROGRESS:
                record.consecutive_no_progress += 1
                current.no_progress_reason = prog.reason
                current.progress_evidence = prog.evidence
            elif prog.progress_status is ProgressStatus.PROGRESS:
                record.consecutive_no_progress = 0
                current.progress_evidence = prog.evidence
            if current.progress_state_fingerprint:
                hist = list(record.progress_fingerprint_history)
                hist.append(current.progress_state_fingerprint)
                record.progress_fingerprint_history = hist[
                    -self.orch_config.oscillation_history_window :
                ]
            current.round_result = verdict or "unknown"
            self.orch_store.save_round(current)

        decision = detect_stalemate(
            self.orch_store.load_rounds(record.orchestration_id),
            history=record.progress_fingerprint_history,
            consecutive_no_progress=record.consecutive_no_progress,
            consecutive_malformed=record.consecutive_malformed,
            config=self.orch_config,
        )
        if decision.stalemate:
            if current:
                current.stalemate_evidence = decision.evidence
                self.orch_store.save_round(current)
            return self._stalemate_stop(record, decision.reason, decision.failure_class)

        if verdict == "pass" or (
            verdict == "pass_with_notes" and self.orch_config.allow_pass_with_notes_completion
        ):
            # Blocking findings in pass_with_notes?
            if verdict == "pass_with_notes" and current:
                blocking = [
                    f
                    for f in current.canonical_findings
                    if f.severity in ("blocker", "major")
                ]
                if blocking:
                    return self._transition(
                        record,
                        OrchestrationState.REPAIR_REQUIRED,
                        notes="pass_with_notes has blocking findings",
                        failure_class=OrchestrationFailureClass.CHANGES_REQUIRED,
                    )
            task = self.task_store.load(record.task_id)
            if task.status is TaskStatus.READY_FOR_REVIEW:
                task = apply_status_transition(task, TaskStatus.REVIEW_PASSED)
                self.task_store.update(task)
            record = self._transition(
                record, OrchestrationState.COMPLETED, notes=f"review {verdict}"
            )
            self._write_summary(record)
            self._active_round = None
            return record

        if verdict == "changes_required":
            if record.current_repair_round >= record.maximum_repair_rounds:
                target = OrchestrationState(self.orch_config.repair_limit_state)
                return self._block(
                    record,
                    f"Repair-round limit reached ({record.maximum_repair_rounds})",
                    OrchestrationFailureClass.REPAIR_LIMIT_REACHED,
                    state=target if target in TERMINAL_ORCH_STATES else OrchestrationState.BLOCKED,
                )
            task = self.task_store.load(record.task_id)
            if task.status is TaskStatus.READY_FOR_REVIEW:
                task = apply_status_transition(task, TaskStatus.REVIEW_FAILED)
                self.task_store.update(task)
            return self._transition(
                record,
                OrchestrationState.REPAIR_REQUIRED,
                notes="review changes_required",
                failure_class=OrchestrationFailureClass.CHANGES_REQUIRED,
            )

        if verdict == "blocked":
            return self._block(
                record, "Review verdict blocked", OrchestrationFailureClass.POLICY_REJECTED
            )

        return self._block(
            record,
            f"Invalid or missing review verdict: {verdict!r}",
            OrchestrationFailureClass.REVIEW_RESULT_INVALID,
        )

    def _stalemate_stop(
        self,
        record: OrchestrationRecord,
        reason: str,
        failure_class: OrchestrationFailureClass,
    ) -> OrchestrationRecord:
        record.stalemate_status = StalemateStatus.DETECTED.value
        record.stop_reason = reason
        record.human_action_requirement = "human review required (stalemate)"
        target = OrchestrationState(self.orch_config.stalemate_state)
        if target not in TERMINAL_ORCH_STATES:
            target = OrchestrationState.HUMAN_REVIEW_REQUIRED
        record = self._block(record, reason, failure_class, state=target)
        self._active_round = None
        return record

    def _open_repair(self, record: OrchestrationRecord) -> OrchestrationRecord:
        if record.current_repair_round >= record.maximum_repair_rounds:
            target = OrchestrationState(self.orch_config.repair_limit_state)
            return self._block(
                record,
                f"Repair-round limit reached ({record.maximum_repair_rounds})",
                OrchestrationFailureClass.REPAIR_LIMIT_REACHED,
                state=target if target in TERMINAL_ORCH_STATES else OrchestrationState.BLOCKED,
            )

        # Stalemate check before another repair
        decision = detect_stalemate(
            self.orch_store.load_rounds(record.orchestration_id),
            history=record.progress_fingerprint_history,
            consecutive_no_progress=record.consecutive_no_progress,
            consecutive_malformed=record.consecutive_malformed,
            config=self.orch_config,
        )
        if decision.stalemate:
            return self._stalemate_stop(record, decision.reason, decision.failure_class)

        next_round = record.current_repair_round + 1
        if next_round > record.maximum_repair_rounds:
            target = OrchestrationState(self.orch_config.repair_limit_state)
            return self._block(
                record,
                f"Repair-round limit reached ({record.maximum_repair_rounds})",
                OrchestrationFailureClass.REPAIR_LIMIT_REACHED,
                state=target if target in TERMINAL_ORCH_STATES else OrchestrationState.BLOCKED,
            )

        record.current_repair_round = next_round
        # Record into existing RepairRoundStore
        try:
            rr = RepairRound(
                task_id=record.task_id,
                round_number=next_round,
                reason=record.review_verdict or record.test_status or "repair",
                result="in_progress",
            )
            self.repair_store.record(
                rr, task_store=self.task_store, max_rounds=record.maximum_repair_rounds
            )
        except ValidationError as exc:
            return self._block(
                record,
                str(exc),
                OrchestrationFailureClass.REPAIR_LIMIT_REACHED,
            )

        self._active_round = None
        record = self._transition(
            record,
            OrchestrationState.REPAIR_PENDING,
            notes=f"opened repair round {next_round}",
        )
        return record


def ORCH_TRANSITIONS_SAFE(state: OrchestrationState):
    from .orchestration_models import ORCH_TRANSITIONS

    return ORCH_TRANSITIONS.get(state, frozenset())
