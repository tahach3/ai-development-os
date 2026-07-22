"""Deterministic dependency-policy checks (not vulnerability scanning)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Categories refused by Round 4A policy (orchestration frameworks / paid SDK defaults).
DEFAULT_PROHIBITED = frozenset(
    {
        "langchain",
        "langchain-core",
        "langchain-community",
        "crewai",
        "autogen",
        "pyautogen",
        "openai",
        "anthropic",
        "google-generativeai",
    }
)

URL_OR_VCS_RE = re.compile(
    r"""(?ix)
    ^(git\+|hg\+|svn\+|bzr\+)
    |://
    |^https?://
    |^ssh://
    |^git@
    |^file://
    """
)

EDITABLE_ABS_RE = re.compile(r"""(?ix)^\s*(-e\s+)?(/|[a-z]:\\)""")


@dataclass
class DependencyFinding:
    name: str
    detail: str
    category: str
    blocker: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "category": self.category,
            "blocker": self.blocker,
        }


@dataclass
class DependencyPolicyResult:
    ok: bool
    runtime_deps: list[str] = field(default_factory=list)
    dev_deps: list[str] = field(default_factory=list)
    findings: list[DependencyFinding] = field(default_factory=list)
    vulnerability_scanning: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "runtime_deps": list(self.runtime_deps),
            "dev_deps": list(self.dev_deps),
            "findings": [f.to_dict() for f in self.findings],
            "vulnerability_scanning": False,
            "notes": list(self.notes)
            + [
                "dependency-policy only; no vulnerability database was queried",
            ],
        }


def _normalize_req(req: str) -> tuple[str, str]:
    text = req.strip()
    # PEP 508 name before extras/version
    name = re.split(r"[<>=!~;\[]", text, maxsplit=1)[0].strip().lower()
    return name, text


def _is_url_or_vcs(req: str) -> bool:
    return bool(URL_OR_VCS_RE.search(req.strip()))


def _is_editable_or_abs(req: str) -> bool:
    s = req.strip()
    if s.startswith("-e ") or s.startswith("--editable"):
        return True
    if EDITABLE_ABS_RE.match(s):
        return True
    if re.match(r"^[A-Za-z]:\\", s) or s.startswith("/"):
        return True
    return False


def check_dependency_policy(
    repo_root: Path,
    *,
    prohibited_names: list[str] | None = None,
) -> DependencyPolicyResult:
    """Validate pyproject dependency declarations. Does not query vuln DBs."""
    pyproject = Path(repo_root) / "pyproject.toml"
    findings: list[DependencyFinding] = []
    if not pyproject.exists():
        findings.append(
            DependencyFinding(
                name="pyproject.toml",
                detail="pyproject.toml missing",
                category="file_consistency",
            )
        )
        return DependencyPolicyResult(ok=False, findings=findings)

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — report as finding
        findings.append(
            DependencyFinding(
                name="pyproject.toml",
                detail=f"unreadable pyproject.toml: {exc}",
                category="file_consistency",
            )
        )
        return DependencyPolicyResult(ok=False, findings=findings)

    project = data.get("project") or {}
    runtime = list(project.get("dependencies") or [])
    opt = project.get("optional-dependencies") or {}
    dev = list(opt.get("dev") or [])
    prohibited = {n.lower() for n in (prohibited_names or [])} | set(DEFAULT_PROHIBITED)

    runtime_names: list[str] = []
    dev_names: list[str] = []

    for label, reqs, sink in (
        ("runtime", runtime, runtime_names),
        ("dev", dev, dev_names),
    ):
        for req in reqs:
            if not isinstance(req, str):
                findings.append(
                    DependencyFinding(
                        name=str(req),
                        detail=f"non-string {label} dependency",
                        category="malformed",
                    )
                )
                continue
            name, full = _normalize_req(req)
            sink.append(full)
            if _is_url_or_vcs(full):
                findings.append(
                    DependencyFinding(
                        name=name or full,
                        detail=f"unpinned URL/VCS dependency refused: {full}",
                        category="url_or_vcs",
                    )
                )
            if _is_editable_or_abs(full):
                findings.append(
                    DependencyFinding(
                        name=name or full,
                        detail=f"editable/absolute path dependency refused: {full}",
                        category="editable_or_absolute",
                    )
                )
            if name in prohibited:
                findings.append(
                    DependencyFinding(
                        name=name,
                        detail=f"prohibited dependency category: {name}",
                        category="prohibited_category",
                    )
                )

    requires = str(project.get("requires-python") or "")
    if requires and "3.11" not in requires and requires != ">=3.11":
        # Soft consistency: must claim 3.11+
        if not requires.startswith(">="):
            findings.append(
                DependencyFinding(
                    name="requires-python",
                    detail=f"unexpected requires-python: {requires}",
                    category="file_consistency",
                    blocker=False,
                )
            )

    ok = not any(f.blocker for f in findings)
    return DependencyPolicyResult(
        ok=ok,
        runtime_deps=runtime_names,
        dev_deps=dev_names,
        findings=findings,
        vulnerability_scanning=False,
    )
