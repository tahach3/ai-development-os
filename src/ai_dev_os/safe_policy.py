"""Allowlists and policy checks for Round 3A safe local execution."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence

from .project_registry import EQUITIFY_SENTINELS
from .validation import is_path_under


class PolicyError(ValueError):
    """Raised when an execution request violates Round 3A policy."""


ALLOWED_EXECUTABLE_BASENAMES = frozenset(
    {
        "python",
        "python.exe",
        "git",
        "git.exe",
    }
)

# Agent / shell tools never permitted via safe_exec.
BLOCKED_EXECUTABLE_BASENAMES = frozenset(
    {
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "bash",
        "bash.exe",
        "sh",
        "sh.exe",
        "zsh",
        "claude",
        "claude.exe",
        "cursor",
        "cursor.exe",
        "codex",
        "codex.exe",
        "npm",
        "npm.cmd",
        "node",
        "node.exe",
    }
)

ALLOWED_PYTEST_FLAGS = frozenset(
    {
        "-q",
        "-v",
        "-x",
        "--tb=short",
        "--tb=line",
        "--tb=no",
    }
)

SHELL_META_RE = re.compile(r"[|&;`$><\n\r]")

SECRET_ENV_RE = re.compile(
    r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|OPENAI|ANTHROPIC|AWS_|PRIVATE[_-]?KEY)",
    re.IGNORECASE,
)

ALLOWED_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
        "COMSPEC",
    }
)

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 120.0
DEFAULT_OUTPUT_LIMIT_BYTES = 65_536

GIT_WORKTREE_SUBCOMMANDS = frozenset({"add", "list", "remove"})


def contains_shell_metacharacters(token: str) -> bool:
    return bool(SHELL_META_RE.search(token))


def assert_no_shell_metacharacters(tokens: Sequence[str]) -> None:
    for token in tokens:
        if contains_shell_metacharacters(token):
            raise PolicyError(
                f"Shell metacharacters refused in argument: {token!r}"
            )


def assert_not_equitify_blob(*parts: str) -> None:
    blob = " ".join(parts).lower().replace("\\", "/")
    for sentinel in EQUITIFY_SENTINELS:
        if sentinel in blob:
            raise PolicyError(
                "Equitify paths and names are refused until explicitly connected"
            )


def executable_basename(executable: str | Path) -> str:
    return Path(executable).name.lower()


def resolve_python_executable() -> str:
    return sys.executable


def assert_executable_allowed(executable: str | Path) -> str:
    base = executable_basename(executable)
    if base in BLOCKED_EXECUTABLE_BASENAMES:
        raise PolicyError(f"Unsupported executable refused: {base}")
    if base not in ALLOWED_EXECUTABLE_BASENAMES:
        raise PolicyError(f"Unsupported executable refused: {base}")
    return base


def clamp_timeout(timeout: float | None) -> float:
    value = DEFAULT_TIMEOUT_SECONDS if timeout is None else float(timeout)
    if value <= 0:
        raise PolicyError("Timeout must be positive")
    if value > MAX_TIMEOUT_SECONDS:
        raise PolicyError(
            f"Timeout {value} exceeds hard ceiling {MAX_TIMEOUT_SECONDS}"
        )
    return value


def filter_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    import os

    raw = source if source is not None else os.environ
    filtered: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ALLOWED_ENV_KEYS:
            continue
        if SECRET_ENV_RE.search(key):
            continue
        filtered[key] = value
    # Nested pytest under harness mutations must not leave .pyc that can be
    # reused after same-second, same-size source rewrites (CPython mtime secs).
    filtered["PYTHONDONTWRITEBYTECODE"] = "1"
    return filtered


def assert_path_confined(path: str | Path, root: str | Path) -> Path:
    """Resolve path and require it under root; reject Equitify and escapes."""
    assert_not_equitify_blob(str(path), str(root))
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if not is_path_under(str(resolved), str(root_resolved)):
        raise PolicyError(
            f"Path escape refused: '{resolved}' is not under '{root_resolved}'"
        )
    return resolved


def build_pytest_argv(
    *,
    test_paths: Sequence[str],
    extra_flags: Sequence[str] | None = None,
    python_executable: str | None = None,
) -> list[str]:
    """Build allowlisted pytest argv. Paths are caller-validated separately."""
    exe = python_executable or resolve_python_executable()
    assert_executable_allowed(exe)
    flags = list(extra_flags or ["-q"])
    for flag in flags:
        if flag == "-k":
            continue
        if flag.startswith("-k="):
            assert_no_shell_metacharacters([flag[3:]])
            continue
        if flag not in ALLOWED_PYTEST_FLAGS:
            raise PolicyError(f"Unsupported pytest flag: {flag}")
    assert_no_shell_metacharacters([*flags, *test_paths])
    for path in test_paths:
        if path.startswith("-"):
            raise PolicyError(f"Test path must not look like a flag: {path}")
    argv = [exe, "-m", "pytest", *flags, *test_paths]
    return argv


def validate_pytest_argv(argv: Sequence[str]) -> None:
    if len(argv) < 3:
        raise PolicyError("pytest argv too short")
    assert_executable_allowed(argv[0])
    if argv[1] != "-m" or argv[2] != "pytest":
        raise PolicyError("Only 'python -m pytest' is permitted for test execution")
    i = 3
    while i < len(argv):
        token = argv[i]
        if token == "-k":
            if i + 1 >= len(argv):
                raise PolicyError("-k requires an expression argument")
            assert_no_shell_metacharacters([argv[i + 1]])
            i += 2
            continue
        if token.startswith("-"):
            if token.startswith("-k="):
                assert_no_shell_metacharacters([token[3:]])
                i += 1
                continue
            if token not in ALLOWED_PYTEST_FLAGS:
                raise PolicyError(f"Unsupported pytest flag: {token}")
            i += 1
            continue
        assert_no_shell_metacharacters([token])
        i += 1
