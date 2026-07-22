"""High-level Round 3A: run targeted pytest inside an isolated session."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .execution_audit import ExecutionAuditStore
from .execution_models import ExecutionEnvelope, rejected_envelope
from .safe_exec import run_allowlisted
from .safe_policy import (
    PolicyError,
    assert_path_confined,
    build_pytest_argv,
    validate_pytest_argv,
)
from .session_store import SessionError, SessionStore
from .worktrees import read_head


def run_session_tests(
    session_id: str,
    *,
    test_paths: Sequence[str] | None = None,
    timeout: float | None = None,
    output_limit_bytes: int | None = None,
    session_store: SessionStore | None = None,
    audit_store: ExecutionAuditStore | None = None,
    extra_flags: Sequence[str] | None = None,
) -> ExecutionEnvelope:
    """Policy-checked targeted pytest for an active session worktree."""
    sessions = session_store or SessionStore()
    audits = audit_store or ExecutionAuditStore(
        workspace_root=sessions.workspace_root
    )

    try:
        record = sessions.require_active(session_id)
    except SessionError as exc:
        env = rejected_envelope(
            session_id=session_id,
            project_id="",
            reason=str(exc),
        )
        audits.save(env)
        return env

    worktree = Path(record.worktree_path)
    requested = list(test_paths) if test_paths else []
    if not requested:
        default_tests = worktree / "tests"
        if default_tests.is_dir():
            requested = ["tests"]
        else:
            env = rejected_envelope(
                session_id=record.session_id,
                project_id=record.project_id,
                reason="No test paths provided and no tests/ directory in worktree",
                task_id=record.task_id,
                starting_commit=record.starting_commit,
                working_directory=str(worktree),
            )
            audits.save(env)
            return env

    try:
        # Confine each relative path under the worktree.
        confined_rel: list[str] = []
        for rel in requested:
            candidate = (worktree / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
            assert_path_confined(candidate, worktree)
            # Prefer relative form for pytest argv readability.
            try:
                confined_rel.append(str(candidate.relative_to(worktree.resolve())))
            except ValueError:
                confined_rel.append(str(candidate))

        argv = build_pytest_argv(test_paths=confined_rel, extra_flags=extra_flags)
        validate_pytest_argv(argv)
    except PolicyError as exc:
        env = rejected_envelope(
            session_id=record.session_id,
            project_id=record.project_id,
            reason=str(exc),
            task_id=record.task_id,
            starting_commit=record.starting_commit,
            working_directory=str(worktree),
            tests_requested=requested,
        )
        audits.save(env)
        return env

    kwargs = {
        "argv": argv,
        "working_directory": worktree,
        "confinement_root": worktree,
        "timeout": timeout,
        "session_id": record.session_id,
        "task_id": record.task_id,
        "project_id": record.project_id,
        "starting_commit": record.starting_commit,
        "tests_requested": requested,
        "tests_executed": confined_rel,
        "resulting_commit_reader": lambda: read_head(worktree),
    }
    if output_limit_bytes is not None:
        kwargs["output_limit_bytes"] = output_limit_bytes

    envelope = run_allowlisted(**kwargs)
    audits.save(envelope)
    return envelope
