"""Normalized execution envelopes and session records for Round 3A."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import utc_now_iso


ENVELOPE_SCHEMA_VERSION = "3a.1"
AUTOMATION_STATUS_LOCAL = "local_allowlisted_execution"


class SessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    CLEANED_UP = "cleaned_up"
    FAILED = "failed"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    ERROR = "error"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class SessionRecord:
    session_id: str
    project_id: str
    starting_commit: str
    worktree_path: str
    status: SessionStatus = SessionStatus.CREATED
    task_id: str | None = None
    project_root: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    cleaned_up_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "starting_commit": self.starting_commit,
            "worktree_path": self.worktree_path,
            "project_root": self.project_root,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cleaned_up_at": self.cleaned_up_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        return cls(
            session_id=str(data["session_id"]),
            project_id=str(data["project_id"]),
            starting_commit=str(data["starting_commit"]),
            worktree_path=str(data["worktree_path"]),
            status=SessionStatus(data.get("status", SessionStatus.CREATED.value)),
            task_id=data.get("task_id"),
            project_root=str(data.get("project_root") or ""),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            cleaned_up_at=data.get("cleaned_up_at"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ExecutionEnvelope:
    schema_version: str
    session_id: str
    task_id: str | None
    project_id: str
    executable: str
    argument_array: list[str]
    sanitized_working_directory: str
    started_at: str | None
    finished_at: str | None
    duration_seconds: float | None
    exit_code: int | None
    timeout_status: bool
    stdout_truncated: bool
    stderr_truncated: bool
    stdout: str
    stderr: str
    execution_status: ExecutionStatus
    tests_requested: list[str]
    tests_executed: list[str]
    starting_commit: str
    resulting_commit: str | None
    policy_decision: PolicyDecision
    rejection_reason: str | None
    automation_status: str
    execution_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "executable": self.executable,
            "argument_array": list(self.argument_array),
            "sanitized_working_directory": self.sanitized_working_directory,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "timeout_status": self.timeout_status,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_status": self.execution_status.value,
            "tests_requested": list(self.tests_requested),
            "tests_executed": list(self.tests_executed),
            "starting_commit": self.starting_commit,
            "resulting_commit": self.resulting_commit,
            "policy_decision": self.policy_decision.value,
            "rejection_reason": self.rejection_reason,
            "automation_status": self.automation_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionEnvelope:
        return cls(
            schema_version=str(data.get("schema_version") or ENVELOPE_SCHEMA_VERSION),
            execution_id=str(data.get("execution_id") or ""),
            session_id=str(data.get("session_id") or ""),
            task_id=data.get("task_id"),
            project_id=str(data.get("project_id") or ""),
            executable=str(data.get("executable") or ""),
            argument_array=list(data.get("argument_array") or []),
            sanitized_working_directory=str(
                data.get("sanitized_working_directory") or ""
            ),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_seconds=data.get("duration_seconds"),
            exit_code=data.get("exit_code"),
            timeout_status=bool(data.get("timeout_status")),
            stdout_truncated=bool(data.get("stdout_truncated")),
            stderr_truncated=bool(data.get("stderr_truncated")),
            stdout=str(data.get("stdout") or ""),
            stderr=str(data.get("stderr") or ""),
            execution_status=ExecutionStatus(
                data.get("execution_status") or ExecutionStatus.ERROR.value
            ),
            tests_requested=list(data.get("tests_requested") or []),
            tests_executed=list(data.get("tests_executed") or []),
            starting_commit=str(data.get("starting_commit") or ""),
            resulting_commit=data.get("resulting_commit"),
            policy_decision=PolicyDecision(
                data.get("policy_decision") or PolicyDecision.DENY.value
            ),
            rejection_reason=data.get("rejection_reason"),
            automation_status=str(
                data.get("automation_status") or AUTOMATION_STATUS_LOCAL
            ),
        )


def rejected_envelope(
    *,
    session_id: str,
    project_id: str,
    reason: str,
    task_id: str | None = None,
    starting_commit: str = "",
    executable: str = "",
    argument_array: list[str] | None = None,
    working_directory: str = "",
    tests_requested: list[str] | None = None,
) -> ExecutionEnvelope:
    now = utc_now_iso()
    return ExecutionEnvelope(
        schema_version=ENVELOPE_SCHEMA_VERSION,
        session_id=session_id,
        task_id=task_id,
        project_id=project_id,
        executable=executable,
        argument_array=list(argument_array or []),
        sanitized_working_directory=working_directory,
        started_at=now,
        finished_at=now,
        duration_seconds=0.0,
        exit_code=None,
        timeout_status=False,
        stdout_truncated=False,
        stderr_truncated=False,
        stdout="",
        stderr="",
        execution_status=ExecutionStatus.REJECTED,
        tests_requested=list(tests_requested or []),
        tests_executed=[],
        starting_commit=starting_commit,
        resulting_commit=None,
        policy_decision=PolicyDecision.DENY,
        rejection_reason=reason,
        automation_status=AUTOMATION_STATUS_LOCAL,
    )
