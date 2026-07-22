"""Inspect-only Git safety helpers. No destructive operations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class GitSafetyError(RuntimeError):
    """Raised when git inspection fails or a destructive action is requested."""


ALLOWED_INSPECT_COMMANDS = frozenset(
    {
        "status",
        "branch",
        "rev-parse",
        "diff",
        "log",
        "remote",
        "show",
    }
)

FORBIDDEN_ACTIONS = frozenset(
    {
        "reset",
        "clean",
        "push",
        "rebase",
        "commit",
        "checkout",
        "switch",
        "merge",
        "stash",
        "filter-branch",
        "gc",
    }
)


@dataclass
class GitInspection:
    root: Path
    is_repo: bool
    branch: str | None
    head: str | None
    status_porcelain: str
    remotes: str
    dirty: bool


def _run_git(root: Path, args: Sequence[str], timeout: float = 15.0) -> str:
    if not args:
        raise GitSafetyError("Empty git argument list")
    verb = args[0]
    # Block destructive verbs even if nested oddly.
    if verb in FORBIDDEN_ACTIONS or any(a in FORBIDDEN_ACTIONS for a in args):
        raise GitSafetyError(
            f"Destructive or mutating git action refused: {' '.join(args)}"
        )
    if verb not in ALLOWED_INSPECT_COMMANDS:
        raise GitSafetyError(f"Git command not allowed for inspect-only mode: {verb}")

    cmd = ["git", *args]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitSafetyError(f"git timed out: {' '.join(cmd)}") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise GitSafetyError(f"git {' '.join(args)} failed: {stderr or completed.returncode}")
    return completed.stdout


def is_git_repo(path: str | Path) -> bool:
    root = Path(path)
    if not root.exists():
        return False
    try:
        out = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
        return out.strip().lower() == "true"
    except GitSafetyError:
        return False


def inspect_repo(path: str | Path) -> GitInspection:
    root = Path(path).resolve()
    if not root.exists():
        raise GitSafetyError(f"Path does not exist: {root}")
    if not (root / ".git").exists() and not is_git_repo(root):
        return GitInspection(
            root=root,
            is_repo=False,
            branch=None,
            head=None,
            status_porcelain="",
            remotes="",
            dirty=False,
        )

    branch: str | None
    head: str | None
    try:
        branch = _run_git(root, ["branch", "--show-current"]).strip() or None
    except GitSafetyError:
        branch = None
    try:
        head = _run_git(root, ["rev-parse", "HEAD"]).strip()
    except GitSafetyError:
        head = None
    status = _run_git(root, ["status", "--porcelain"])
    try:
        remotes = _run_git(root, ["remote", "-v"])
    except GitSafetyError:
        remotes = ""
    return GitInspection(
        root=root,
        is_repo=True,
        branch=branch,
        head=head,
        status_porcelain=status,
        remotes=remotes,
        dirty=bool(status.strip()),
    )


def assert_inspect_only(action: str) -> None:
    """Public guard for callers that might request mutation."""
    normalized = action.strip().lower()
    if normalized in FORBIDDEN_ACTIONS or normalized.startswith("reset"):
        raise GitSafetyError(f"Git safety policy forbids action: {action}")
