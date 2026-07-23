"""Round 4E multi-project boundary enforcement — pure, local, deterministic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .ci_config import CIPolicy, ProjectBoundaryRule
from .ci_models import CIFailureClass

_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:from\s+([A-Za-z0-9_.]+)\s+import|import\s+([A-Za-z0-9_.]+))",
)
_QUOTED_PATH_RE = re.compile(r"""['"]([^'"]*[/\\][^'"]+)['"]""")
_TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".pyw",
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".ini",
        ".cfg",
    }
)


@dataclass(frozen=True)
class BoundaryFinding:
    path: str
    project_id: str
    reason: str
    failure_class: str
    detail: str
    blocker: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "project_id": self.project_id,
            "reason": self.reason,
            "failure_class": self.failure_class,
            "detail": self.detail,
            "blocker": self.blocker,
        }


@dataclass
class BoundaryCheckResult:
    ok: bool
    findings: list[BoundaryFinding] = field(default_factory=list)
    failure_classes: list[str] = field(default_factory=list)
    files_examined: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
            "failure_classes": list(self.failure_classes),
            "files_examined": list(self.files_examined),
        }


def normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("./")


def _root_key(root: str) -> str:
    return normalize_rel_path(root).lower().rstrip("/")


def path_under_root(path: str, root: str) -> bool:
    p = normalize_rel_path(path).lower()
    r = _root_key(root)
    if not r:
        return False
    return p == r or p.startswith(r + "/")


def homes_for_path(
    path: str, boundaries: Sequence[ProjectBoundaryRule]
) -> list[ProjectBoundaryRule]:
    hits: list[ProjectBoundaryRule] = []
    for rule in boundaries:
        if any(path_under_root(path, root) for root in rule.allowed_roots):
            hits.append(rule)
    return hits


def _module_to_path(module: str) -> str:
    return module.strip(".").replace(".", "/")


def _extract_import_refs(text: str) -> list[str]:
    refs: list[str] = []
    for line in text.splitlines():
        m = _IMPORT_LINE_RE.match(line)
        if m:
            mod = m.group(1) or m.group(2) or ""
            if mod:
                refs.append(_module_to_path(mod))
        for qm in _QUOTED_PATH_RE.finditer(line):
            refs.append(normalize_rel_path(qm.group(1)))
    return refs


def _forbidden_hit(haystack: str, needles: Sequence[str]) -> str | None:
    low = haystack.lower().replace("\\", "/")
    for needle in needles:
        n = needle.lower().replace("\\", "/").strip()
        if n and n in low:
            return needle
    return None


def _other_project_root_hit(
    ref: str,
    home: ProjectBoundaryRule,
    boundaries: Sequence[ProjectBoundaryRule],
) -> tuple[str, str] | None:
    """If ref falls under another project's allowed_roots, return (project_id, root)."""
    ref_n = normalize_rel_path(ref).lower()
    for rule in boundaries:
        if rule.project_id == home.project_id:
            continue
        for root in rule.allowed_roots:
            r = _root_key(root)
            if not r:
                continue
            if path_under_root(ref, root) or ref_n.startswith(r) or f"/{r}/" in f"/{ref_n}/":
                return rule.project_id, root
    return None


def check_project_boundaries(
    *,
    paths: Sequence[str],
    policy: CIPolicy,
    repo_root: Path | None = None,
    read_content: bool = True,
) -> BoundaryCheckResult:
    """Flag cross-boundary path/import violations. Deterministic; local-only."""
    boundaries = list(policy.project_boundaries)
    unique_paths = sorted({normalize_rel_path(p) for p in paths if p and p.strip()})
    findings: list[BoundaryFinding] = []

    if not boundaries:
        return BoundaryCheckResult(ok=True, findings=[], failure_classes=[], files_examined=unique_paths)

    root = repo_root.resolve() if repo_root is not None else None

    for path in unique_paths:
        homes = homes_for_path(path, boundaries)
        if len(homes) > 1:
            ids = ",".join(sorted(h.project_id for h in homes))
            findings.append(
                BoundaryFinding(
                    path=path,
                    project_id=ids,
                    reason="ambiguous_ownership",
                    failure_class=CIFailureClass.BOUNDARY_CONFIG_AMBIGUOUS.value,
                    detail=f"path owned by multiple project_boundaries: {ids}",
                )
            )
            continue

        # Forbidden substrings: check against all rules (reinforces Equitify needles).
        for rule in boundaries:
            hit = _forbidden_hit(path, rule.forbidden_substrings)
            if hit:
                findings.append(
                    BoundaryFinding(
                        path=path,
                        project_id=rule.project_id,
                        reason="forbidden_substring_path",
                        failure_class=CIFailureClass.BOUNDARY_VIOLATION.value,
                        detail=f"path contains forbidden substring {hit!r}",
                    )
                )

        if not homes:
            continue

        home = homes[0]
        # Nested foreign root inside an otherwise in-scope path.
        cross = _other_project_root_hit(path, home, boundaries)
        if cross and not path_under_root(path, cross[1]):
            other_id, other_root = cross
            findings.append(
                BoundaryFinding(
                    path=path,
                    project_id=home.project_id,
                    reason="cross_boundary_path",
                    failure_class=CIFailureClass.BOUNDARY_VIOLATION.value,
                    detail=(
                        f"path under {home.project_id!r} references other project "
                        f"{other_id!r} root {other_root!r}"
                    ),
                )
            )

        if not read_content or root is None:
            continue
        full = root / path
        if not full.is_file():
            continue
        if full.suffix.lower() not in _TEXT_SUFFIXES and full.suffix != "":
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for ref in _extract_import_refs(text):
            forb = _forbidden_hit(ref, home.forbidden_substrings)
            if forb:
                findings.append(
                    BoundaryFinding(
                        path=path,
                        project_id=home.project_id,
                        reason="forbidden_substring_import",
                        failure_class=CIFailureClass.BOUNDARY_VIOLATION.value,
                        detail=f"import/path ref {ref!r} contains forbidden substring {forb!r}",
                    )
                )
                continue
            other = _other_project_root_hit(ref, home, boundaries)
            if other:
                other_id, other_root = other
                findings.append(
                    BoundaryFinding(
                        path=path,
                        project_id=home.project_id,
                        reason="cross_boundary_import",
                        failure_class=CIFailureClass.BOUNDARY_VIOLATION.value,
                        detail=(
                            f"import/path ref {ref!r} crosses into project "
                            f"{other_id!r} root {other_root!r}"
                        ),
                    )
                )

    # Deterministic order: path, project_id, reason, detail
    findings.sort(key=lambda f: (f.path, f.project_id, f.reason, f.detail))
    # Dedupe identical findings
    deduped: list[BoundaryFinding] = []
    seen: set[tuple[str, str, str, str]] = set()
    for f in findings:
        key = (f.path, f.project_id, f.reason, f.detail)
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    classes: list[str] = []
    for f in deduped:
        if f.failure_class not in classes:
            classes.append(f.failure_class)

    return BoundaryCheckResult(
        ok=not deduped,
        findings=deduped,
        failure_classes=classes,
        files_examined=unique_paths,
    )
