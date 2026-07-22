"""Safe subprocess runner — argument arrays only, never shell=True."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable, Sequence

from .execution_models import (
    AUTOMATION_STATUS_LOCAL,
    ENVELOPE_SCHEMA_VERSION,
    ExecutionEnvelope,
    ExecutionStatus,
    PolicyDecision,
)
from .models import utc_now_iso
from .safe_policy import (
    DEFAULT_OUTPUT_LIMIT_BYTES,
    PolicyError,
    assert_executable_allowed,
    assert_no_shell_metacharacters,
    assert_path_confined,
    clamp_timeout,
    filter_environment,
    validate_pytest_argv,
)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    clipped = raw[:limit].decode("utf-8", errors="replace")
    return clipped + "\n...[truncated]...", True


def run_allowlisted(
    argv: Sequence[str],
    *,
    working_directory: str | Path,
    confinement_root: str | Path,
    timeout: float | None = None,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    env: dict[str, str] | None = None,
    session_id: str = "",
    task_id: str | None = None,
    project_id: str = "",
    starting_commit: str = "",
    tests_requested: list[str] | None = None,
    tests_executed: list[str] | None = None,
    resulting_commit_reader: Callable[[], str | None] | None = None,
) -> ExecutionEnvelope:
    """Run argv with shell=False under confinement. Returns a full envelope."""
    tests_requested = list(tests_requested or [])
    tests_executed = list(tests_executed or [])
    argv_list = [str(a) for a in argv]
    try:
        if not argv_list:
            raise PolicyError("Empty argument array refused")
        base = assert_executable_allowed(argv_list[0])
        if base.startswith("git"):
            raise PolicyError(
                "git must not be invoked via safe_exec; use worktree helpers"
            )
        if base.startswith("python"):
            validate_pytest_argv(argv_list)
        assert_no_shell_metacharacters(argv_list[1:])
        cwd = assert_path_confined(working_directory, confinement_root)
        timeout_s = clamp_timeout(timeout)
        child_env = filter_environment(env)
    except PolicyError as exc:
        from .execution_models import rejected_envelope

        return rejected_envelope(
            session_id=session_id,
            project_id=project_id,
            reason=str(exc),
            task_id=task_id,
            starting_commit=starting_commit,
            executable=argv_list[0] if argv_list else "",
            argument_array=argv_list,
            working_directory=str(working_directory),
            tests_requested=tests_requested,
        )

    started = time.perf_counter()
    started_at = utc_now_iso()
    timeout_hit = False
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    status = ExecutionStatus.ERROR
    rejection: str | None = None

    try:
        completed = subprocess.run(
            argv_list,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
            check=False,
            env=child_env,
        )
        exit_code = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        status = (
            ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.FAILED
        )
    except subprocess.TimeoutExpired as exc:
        timeout_hit = True
        status = ExecutionStatus.TIMEOUT
        exit_code = None
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (
            (exc.stdout or b"").decode("utf-8", errors="replace")
            if exc.stdout
            else ""
        )
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (
            (exc.stderr or b"").decode("utf-8", errors="replace")
            if exc.stderr
            else ""
        )
        rejection = f"Process timed out after {timeout_s}s"
    except OSError as exc:
        status = ExecutionStatus.ERROR
        rejection = f"Failed to spawn process: {exc}"

    finished_at = utc_now_iso()
    duration = round(time.perf_counter() - started, 6)
    stdout_out, stdout_trunc = _truncate(stdout, output_limit_bytes)
    stderr_out, stderr_trunc = _truncate(stderr, output_limit_bytes)

    resulting: str | None = None
    if resulting_commit_reader is not None:
        try:
            resulting = resulting_commit_reader()
        except Exception:
            resulting = None

    return ExecutionEnvelope(
        schema_version=ENVELOPE_SCHEMA_VERSION,
        session_id=session_id,
        task_id=task_id,
        project_id=project_id,
        executable=argv_list[0],
        argument_array=argv_list,
        sanitized_working_directory=str(cwd),
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        exit_code=exit_code,
        timeout_status=timeout_hit,
        stdout_truncated=stdout_trunc,
        stderr_truncated=stderr_trunc,
        stdout=stdout_out,
        stderr=stderr_out,
        execution_status=status,
        tests_requested=tests_requested,
        tests_executed=tests_executed if status != ExecutionStatus.REJECTED else [],
        starting_commit=starting_commit,
        resulting_commit=resulting,
        policy_decision=PolicyDecision.ALLOW,
        rejection_reason=rejection,
        automation_status=AUTOMATION_STATUS_LOCAL,
    )
