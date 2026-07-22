"""Allowlisted git worktree create/list/remove for Round 3A sessions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from .git_safety import FORBIDDEN_ACTIONS
from .safe_policy import (
    GIT_WORKTREE_SUBCOMMANDS,
    PolicyError,
    assert_executable_allowed,
    assert_not_equitify_blob,
    assert_path_confined,
)


class WorktreeError(RuntimeError):
    """Raised when a safe worktree operation fails."""


def _run_git_worktree(
    project_root: Path,
    worktree_args: Sequence[str],
    *,
    timeout: float = 60.0,
) -> str:
    """Run `git worktree <subcommand> ...` only — never shell, never other verbs."""
    if not worktree_args:
        raise PolicyError("Empty worktree argument list")
    sub = worktree_args[0]
    if sub not in GIT_WORKTREE_SUBCOMMANDS:
        raise PolicyError(f"Git worktree subcommand refused: {sub}")
    # Defense: refuse if any forbidden mutating verb appears in args.
    for token in worktree_args:
        if token in FORBIDDEN_ACTIONS:
            raise PolicyError(f"Forbidden git token in worktree args: {token}")

    assert_executable_allowed("git")
    cmd = ["git", "worktree", *worktree_args]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError(f"git worktree timed out: {' '.join(cmd)}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise WorktreeError(f"git worktree {' '.join(worktree_args)} failed: {err}")
    return completed.stdout


def read_head(project_root: Path) -> str:
    assert_not_equitify_blob(str(project_root))
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=15.0,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        raise WorktreeError(
            f"Cannot read HEAD at {project_root}: {(completed.stderr or '').strip()}"
        )
    return completed.stdout.strip()


def require_git_repo(project_root: Path) -> None:
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=15.0,
        shell=False,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip().lower() != "true":
        raise WorktreeError(f"Project root is not a git repository: {project_root}")


def create_session_worktree(
    *,
    project_root: Path,
    worktree_path: Path,
    commit: str,
    sessions_root: Path,
) -> Path:
    """Create a linked worktree under sessions_root for the given commit."""
    assert_not_equitify_blob(str(project_root), str(worktree_path), commit)
    require_git_repo(project_root)
    sessions_root = sessions_root.resolve()
    sessions_root.mkdir(parents=True, exist_ok=True)
    # Parent of worktree must exist; worktree path itself must not.
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        raise WorktreeError(f"Worktree path already exists: {worktree_path}")

    # Confinement: worktree destination must live under sessions_root.
    # Path does not exist yet — confine the intended parent + name via resolve of parent.
    confined_parent = assert_path_confined(worktree_path.parent, sessions_root)
    target = (confined_parent / worktree_path.name).resolve()
    if not str(target).lower().startswith(str(sessions_root.resolve()).lower()):
        raise PolicyError(f"Worktree path escape refused: {target}")

    if not commit or any(c in commit for c in (" ", ";", "|", "&", "$")):
        raise PolicyError(f"Invalid commit ref refused: {commit!r}")

    _run_git_worktree(project_root, ["add", "--detach", str(target), commit])
    return target


def remove_session_worktree(*, project_root: Path, worktree_path: Path) -> None:
    """Remove a linked worktree. Does not reset or clean the main checkout."""
    assert_not_equitify_blob(str(project_root), str(worktree_path))
    path = Path(worktree_path).resolve()
    if not path.exists():
        return
    _run_git_worktree(project_root, ["remove", "--force", str(path)])


def list_worktrees(project_root: Path) -> str:
    return _run_git_worktree(project_root, ["list"])
