"""Fixture-controlled synthetic worktree mutations (never from provider text)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .fingerprints import fingerprint
from .worktrees import read_head


class MutationError(ValueError):
    pass


# Predeclared mutations owned by the harness — not parsed from provider output.
MUTATION_CATALOG: dict[str, dict[str, Any]] = {
    "noop": {
        "description": "No source change",
        "files": {},
    },
    "add_subtract": {
        "description": "Add subtract function and test",
        "files": {
            "calculator/ops.py": (
                "def add(a, b):\n    return a + b\n\n"
                "def subtract(a, b):\n    return a - b\n"
            ),
            "tests/test_ops.py": (
                "from calculator.ops import add, subtract\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n"
                "def test_subtract():\n    assert subtract(5, 2) == 3\n"
            ),
        },
    },
    "add_subtract_buggy": {
        "description": "Introduce buggy subtract (tests fail)",
        "files": {
            "calculator/ops.py": (
                "def add(a, b):\n    return a + b\n\n"
                "def subtract(a, b):\n    return a + b\n"
            ),
            "tests/test_ops.py": (
                "from calculator.ops import add, subtract\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n"
                "def test_subtract():\n    assert subtract(5, 2) == 3\n"
            ),
        },
    },
    "add_subtract_fixed": {
        "description": "Fix subtract",
        "files": {
            "calculator/ops.py": (
                "def add(a, b):\n    return a + b\n\n"
                "def subtract(a, b):\n    return a - b\n"
            ),
            "tests/test_ops.py": (
                "from calculator.ops import add, subtract\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n"
                "def test_subtract():\n    assert subtract(5, 2) == 3\n"
            ),
        },
    },
    "cosmetic_only": {
        "description": "Comment-only change on correct code (tests still pass)",
        "files": {
            "calculator/ops.py": (
                "def add(a, b):\n    return a + b  # cosmetic\n\n"
                "def subtract(a, b):\n    return a - b  # still correct\n"
            ),
        },
    },
    "oscillation_a": {
        "description": "Oscillation state A (tests pass; review-facing marker)",
        "files": {
            "calculator/ops.py": (
                "def add(a, b):\n    return a + b\n\n"
                "def subtract(a, b):\n    return a - b  # marker-a\n"
            ),
        },
    },
    "oscillation_b": {
        "description": "Oscillation state B (tests pass; review-facing marker)",
        "files": {
            "calculator/ops.py": (
                "def add(a, b):\n    return a + b\n\n"
                "def subtract(a, b):\n    return a - b  # marker-b\n"
            ),
        },
    },
}


def apply_fixture_mutation(
    worktree: Path,
    mutation_id: str,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    """Apply a catalog mutation inside a synthetic worktree only."""
    if mutation_id not in MUTATION_CATALOG:
        raise MutationError(f"Unknown harness mutation: {mutation_id}")
    spec = MUTATION_CATALOG[mutation_id]
    root = worktree.resolve()
    changed: list[str] = []
    for rel, content in (spec.get("files") or {}).items():
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise MutationError(f"Mutation path escapes worktree: {rel}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        changed.append(rel.replace("\\", "/"))

    if commit and changed:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=orch@ai-dev-os.local",
                "-c",
                "user.name=OrchestrationHarness",
                "commit",
                "-m",
                f"harness mutation {mutation_id}",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )

    head = read_head(root) if (root / ".git").exists() or (root / ".git").is_file() else ""
    diff_fp = fingerprint(
        {
            "mutation_id": mutation_id,
            "files": sorted(changed),
            "contents": {k: fingerprint(v) for k, v in sorted((spec.get("files") or {}).items())},
        }
    )
    return {
        "mutation_id": mutation_id,
        "files_changed": changed,
        "commit": head,
        "diff_fingerprint": diff_fp,
    }


def worktree_content_fingerprint(worktree: Path, rel_paths: list[str] | None = None) -> str:
    root = worktree.resolve()
    paths = rel_paths or ["calculator/ops.py", "tests/test_ops.py"]
    payload: dict[str, str] = {}
    for rel in paths:
        p = root / rel
        if p.is_file():
            payload[rel.replace("\\", "/")] = p.read_text(encoding="utf-8")
    return fingerprint(payload)
