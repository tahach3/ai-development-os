"""Round 4A CI models, enums, and schema constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .models import utc_now_iso


CI_SCHEMA_VERSION = "4a.1"
CI_POLICY_VERSION = "4a.1"


class CITriggerType(str, Enum):
    LOCAL = "local"
    PULL_REQUEST = "pull_request"
    PUSH = "push"
    WORKFLOW_DISPATCH = "workflow_dispatch"
    VALIDATE_CHANGE = "validate_change"


class CIRunState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class CIStageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    ERROR = "error"


class CIVerdict(str, Enum):
    PASS = "pass"
    PASS_WITH_NOTES = "pass_with_notes"
    FAIL = "fail"
    BLOCKED = "blocked"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class CIFailureClass(str, Enum):
    NONE = "none"
    REPO_IDENTITY_FAILED = "repo_identity_failed"
    PYTHON_COMPILE_FAILED = "python_compile_failed"
    TESTS_FAILED = "tests_failed"
    GIT_DIFF_CHECK_FAILED = "git_diff_check_failed"
    MALFORMED_SCHEMA = "malformed_schema"
    MALFORMED_CONFIG = "malformed_config"
    REGISTRY_INVALID = "registry_invalid"
    PROHIBITED_PATH = "prohibited_path"
    PACKAGE_VERSION_MISMATCH = "package_version_mismatch"
    DEPENDENCY_POLICY_VIOLATED = "dependency_policy_violated"
    SECRET_PATTERN_DETECTED = "secret_pattern_detected"
    RUNTIME_ARTIFACT_DETECTED = "runtime_artifact_detected"
    DOC_INCONSISTENCY = "doc_inconsistency"
    TIMEOUT = "timeout"
    COMMAND_REJECTED = "command_rejected"
    UNSAFE_WORKFLOW = "unsafe_workflow"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    INTERNAL_ERROR = "internal_error"
    POLICY_REJECTED = "policy_rejected"
    BOUNDARY_VIOLATION = "boundary_violation"
    BOUNDARY_CONFIG_AMBIGUOUS = "boundary_config_ambiguous"
    BOUNDARY_CONFIG_INVALID = "boundary_config_invalid"


STAGE_ORDER: tuple[str, ...] = (
    "repo_identity",
    "python_compile",
    "pytest_suite",
    "git_diff_check",
    "schema_validation",
    "config_parse",
    "project_registry",
    "prohibited_paths",
    "package_version",
    "dependency_policy",
    "secret_scan",
    "runtime_artifacts",
    "doc_consistency",
    "finalize",
)


def new_ci_run_id() -> str:
    return f"ci_{uuid4().hex[:12]}"


@dataclass
class CIStageResult:
    schema_version: str = CI_SCHEMA_VERSION
    ci_policy_version: str = CI_POLICY_VERSION
    stage_name: str = ""
    command_identity: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    exit_status: int | None = None
    timeout_status: bool = False
    validation_status: str = CIStageStatus.PENDING.value
    failure_class: str = CIFailureClass.NONE.value
    sanitized_output_summary: str = ""
    truncation_status: bool = False
    files_examined: list[str] = field(default_factory=list)
    policy_decision: str = "allow"
    blocker: bool = False
    next_action: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ci_policy_version": self.ci_policy_version,
            "stage_name": self.stage_name,
            "command_identity": self.command_identity,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "exit_status": self.exit_status,
            "timeout_status": self.timeout_status,
            "validation_status": self.validation_status,
            "failure_class": self.failure_class,
            "sanitized_output_summary": self.sanitized_output_summary,
            "truncation_status": self.truncation_status,
            "files_examined": list(self.files_examined),
            "policy_decision": self.policy_decision,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CIStageResult":
        return cls(
            schema_version=str(data.get("schema_version", CI_SCHEMA_VERSION)),
            ci_policy_version=str(data.get("ci_policy_version", CI_POLICY_VERSION)),
            stage_name=str(data.get("stage_name", "")),
            command_identity=str(data.get("command_identity", "")),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            duration_seconds=float(data.get("duration_seconds", 0.0) or 0.0),
            exit_status=data.get("exit_status"),
            timeout_status=bool(data.get("timeout_status", False)),
            validation_status=str(
                data.get("validation_status", CIStageStatus.PENDING.value)
            ),
            failure_class=str(data.get("failure_class", CIFailureClass.NONE.value)),
            sanitized_output_summary=str(data.get("sanitized_output_summary", "")),
            truncation_status=bool(data.get("truncation_status", False)),
            files_examined=list(data.get("files_examined") or []),
            policy_decision=str(data.get("policy_decision", "allow")),
            blocker=bool(data.get("blocker", False)),
            next_action=str(data.get("next_action", "")),
            notes=list(data.get("notes") or []),
        )


@dataclass
class CIRun:
    schema_version: str = CI_SCHEMA_VERSION
    ci_policy_version: str = CI_POLICY_VERSION
    run_id: str = field(default_factory=new_ci_run_id)
    repository_identity: str = ""
    starting_commit: str = ""
    compared_base_commit: str | None = None
    trigger_type: str = CITriggerType.LOCAL.value
    state: str = CIRunState.CREATED.value
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    stages: list[CIStageResult] = field(default_factory=list)
    final_verdict: str = CIVerdict.FAIL.value
    failure_classes: list[str] = field(default_factory=list)
    human_review_required: bool = False
    blocker: bool = False
    next_action: str = ""
    policy_decision: str = "allow"
    tests_passed: int | None = None
    tests_failed: int | None = None
    tests_skipped: int | None = None
    sanitized_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ci_policy_version": self.ci_policy_version,
            "run_id": self.run_id,
            "repository_identity": self.repository_identity,
            "starting_commit": self.starting_commit,
            "compared_base_commit": self.compared_base_commit,
            "trigger_type": self.trigger_type,
            "state": self.state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "stages": [s.to_dict() for s in self.stages],
            "final_verdict": self.final_verdict,
            "failure_classes": list(self.failure_classes),
            "human_review_required": self.human_review_required,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "policy_decision": self.policy_decision,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "sanitized_notes": list(self.sanitized_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CIRun":
        sv = str(data.get("schema_version", ""))
        if sv and sv != CI_SCHEMA_VERSION:
            raise ValueError(f"Unsupported CI schema version: {sv}")
        stages_raw = data.get("stages") or []
        stages = [
            CIStageResult.from_dict(s) if isinstance(s, dict) else s for s in stages_raw
        ]
        return cls(
            schema_version=str(data.get("schema_version", CI_SCHEMA_VERSION)),
            ci_policy_version=str(data.get("ci_policy_version", CI_POLICY_VERSION)),
            run_id=str(data.get("run_id") or new_ci_run_id()),
            repository_identity=str(data.get("repository_identity", "")),
            starting_commit=str(data.get("starting_commit", "")),
            compared_base_commit=data.get("compared_base_commit"),
            trigger_type=str(data.get("trigger_type", CITriggerType.LOCAL.value)),
            state=str(data.get("state", CIRunState.CREATED.value)),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            duration_seconds=float(data.get("duration_seconds", 0.0) or 0.0),
            stages=stages,
            final_verdict=str(data.get("final_verdict", CIVerdict.FAIL.value)),
            failure_classes=list(data.get("failure_classes") or []),
            human_review_required=bool(data.get("human_review_required", False)),
            blocker=bool(data.get("blocker", False)),
            next_action=str(data.get("next_action", "")),
            policy_decision=str(data.get("policy_decision", "allow")),
            tests_passed=data.get("tests_passed"),
            tests_failed=data.get("tests_failed"),
            tests_skipped=data.get("tests_skipped"),
            sanitized_notes=list(data.get("sanitized_notes") or []),
        )


@dataclass
class PRValidationFinding:
    path: str
    category: str
    severity: str
    summary: str
    failure_class: str = CIFailureClass.NONE.value
    human_review_required: bool = False
    blocker: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "category": self.category,
            "severity": self.severity,
            "summary": self.summary,
            "failure_class": self.failure_class,
            "human_review_required": self.human_review_required,
            "blocker": self.blocker,
        }


@dataclass
class PRValidationSummary:
    schema_version: str = CI_SCHEMA_VERSION
    ci_policy_version: str = CI_POLICY_VERSION
    run_id: str = field(default_factory=new_ci_run_id)
    repository_identity: str = ""
    starting_commit: str = ""
    compared_base_commit: str | None = None
    trigger_type: str = CITriggerType.VALIDATE_CHANGE.value
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    files_examined: list[str] = field(default_factory=list)
    findings: list[PRValidationFinding] = field(default_factory=list)
    final_verdict: str = CIVerdict.PASS.value
    failure_classes: list[str] = field(default_factory=list)
    human_review_required: bool = False
    blocker: bool = False
    next_action: str = "no automatic merge or approve"
    policy_decision: str = "report_only"
    auto_approve: bool = False
    auto_merge: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ci_policy_version": self.ci_policy_version,
            "run_id": self.run_id,
            "repository_identity": self.repository_identity,
            "starting_commit": self.starting_commit,
            "compared_base_commit": self.compared_base_commit,
            "trigger_type": self.trigger_type,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "files_examined": list(self.files_examined),
            "findings": [f.to_dict() for f in self.findings],
            "final_verdict": self.final_verdict,
            "failure_classes": list(self.failure_classes),
            "human_review_required": self.human_review_required,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "policy_decision": self.policy_decision,
            "auto_approve": False,
            "auto_merge": False,
        }
