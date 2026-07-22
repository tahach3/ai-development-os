"""Bounded subprocess helper for CI stages — argv only, sanitized env."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .ci_secrets import redact_secrets
from .safe_policy import (
    DEFAULT_OUTPUT_LIMIT_BYTES,
    SHELL_META_RE,
    filter_environment,
)


class CICommandError(RuntimeError):
    """Raised when a CI command is rejected before execution."""


@dataclass
class CICommandResult:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    truncated: bool
    rejected: str | None = None


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    clipped = raw[:limit].decode("utf-8", errors="replace")
    return clipped + "\n...[truncated]...", True


def assert_argv_safe(argv: Sequence[str]) -> list[str]:
    if not argv:
        raise CICommandError("Empty argument array refused")
    out = [str(a) for a in argv]
    for token in out[1:]:
        if SHELL_META_RE.search(token):
            raise CICommandError(f"Shell metacharacter refused in argv: {token!r}")
        if token.strip() == "-c" and "python" in Path(out[0]).name.lower():
            raise CICommandError("python -c payloads refused in CI runner")
    # Refuse obvious shell wrappers
    base = Path(out[0]).name.lower()
    if base in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "bash", "sh"}:
        raise CICommandError(f"Shell executable refused: {base}")
    return out


def run_ci_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    env: dict[str, str] | None = None,
) -> CICommandResult:
    argv_list = assert_argv_safe(argv)
    child_env = filter_environment(env if env is not None else dict(os.environ))
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv_list,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
            env=child_env,
        )
        stdout, t1 = _truncate(completed.stdout or "", output_limit_bytes)
        stderr, t2 = _truncate(completed.stderr or "", output_limit_bytes)
        return CICommandResult(
            argv=argv_list,
            exit_code=int(completed.returncode),
            stdout=redact_secrets(stdout),
            stderr=redact_secrets(stderr),
            duration_seconds=time.perf_counter() - started,
            timed_out=False,
            truncated=t1 or t2,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = ""
        stderr = ""
        if isinstance(exc.stdout, str):
            stdout = exc.stdout
        elif exc.stdout:
            stdout = exc.stdout.decode("utf-8", errors="replace")
        if isinstance(exc.stderr, str):
            stderr = exc.stderr
        elif exc.stderr:
            stderr = exc.stderr.decode("utf-8", errors="replace")
        stdout, t1 = _truncate(stdout, output_limit_bytes)
        stderr, t2 = _truncate(stderr, output_limit_bytes)
        return CICommandResult(
            argv=argv_list,
            exit_code=None,
            stdout=redact_secrets(stdout),
            stderr=redact_secrets(stderr),
            duration_seconds=time.perf_counter() - started,
            timed_out=True,
            truncated=t1 or t2,
        )
