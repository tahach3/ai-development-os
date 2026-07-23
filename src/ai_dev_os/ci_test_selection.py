"""Round 4A hardening — deterministic targeted / related-module test selection.

Maps a set of changed files to the smallest *safe* set of pytest targets so a
change can be validated fast, without paying for the whole suite on every
iteration. This is purely additive: it never mutates the fixed Round 4A CI
``STAGE_ORDER`` and never replaces the authoritative full ``pytest_suite``
stage — it is a separate, opt-in fast gate that reuses the same argv-only,
sanitized-environment, timeout-bounded runner.

Selection is fail-safe by construction: when a change touches a broad-impact
file (package ``__init__``, shared models, the CLI, packaging, config, or
schemas) the whole suite is selected rather than guessing a subset. When code
changes map to no related test, that is reported so the caller can fall back to
the full suite instead of silently passing.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

from .ci_config import CIPolicy, load_ci_policy
from .ci_models import CI_POLICY_VERSION, CI_SCHEMA_VERSION, CIVerdict
from .ci_runner import CICommandError, run_ci_command
from .models import utc_now_iso

PACKAGE_DIR = "src/ai_dev_os"
TESTS_DIR = "tests"

# Changing any of these plausibly affects many tests, so we over-select the
# whole suite rather than risk a false "green" from a too-narrow subset.
DEFAULT_BROAD_IMPACT_GLOBS: tuple[str, ...] = (
    "src/ai_dev_os/__init__.py",
    "src/ai_dev_os/models.py",
    "src/ai_dev_os/cli.py",
    "pyproject.toml",
    "conftest.py",
    "tests/conftest.py",
    "config/**",
    "schemas/**",
)


def new_selection_id() -> str:
    return f"cisel_{uuid4().hex[:12]}"


@dataclass
class TargetedSelection:
    """Deterministic mapping from changed files to related test files."""

    schema_version: str = CI_SCHEMA_VERSION
    ci_policy_version: str = CI_POLICY_VERSION
    changed_files: list[str] = field(default_factory=list)
    selected_tests: list[str] = field(default_factory=list)
    unmapped_sources: list[str] = field(default_factory=list)
    broad: bool = False
    reason: str = "no_code_impact"
    rationale: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ci_policy_version": self.ci_policy_version,
            "changed_files": list(self.changed_files),
            "selected_tests": list(self.selected_tests),
            "unmapped_sources": list(self.unmapped_sources),
            "broad": self.broad,
            "reason": self.reason,
            "rationale": {k: list(v) for k, v in sorted(self.rationale.items())},
        }


@dataclass
class TargetedTestRun:
    """Normalized envelope for a targeted (related-module) test execution."""

    schema_version: str = CI_SCHEMA_VERSION
    ci_policy_version: str = CI_POLICY_VERSION
    run_id: str = field(default_factory=new_selection_id)
    repository_identity: str = ""
    starting_commit: str = ""
    compared_base_commit: str | None = None
    command_identity: str = "python -m pytest -q <targeted>"
    selection: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    exit_status: int | None = None
    timeout_status: bool = False
    truncation_status: bool = False
    ran_full_suite: bool = False
    tests_passed: int | None = None
    tests_failed: int | None = None
    tests_skipped: int | None = None
    final_verdict: str = CIVerdict.PASS.value
    failure_class: str = "none"
    sanitized_output_summary: str = ""
    next_action: str = ""
    policy_decision: str = "allow"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ci_policy_version": self.ci_policy_version,
            "run_id": self.run_id,
            "repository_identity": self.repository_identity,
            "starting_commit": self.starting_commit,
            "compared_base_commit": self.compared_base_commit,
            "command_identity": self.command_identity,
            "selection": self.selection,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "exit_status": self.exit_status,
            "timeout_status": self.timeout_status,
            "truncation_status": self.truncation_status,
            "ran_full_suite": self.ran_full_suite,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "final_verdict": self.final_verdict,
            "failure_class": self.failure_class,
            "sanitized_output_summary": self.sanitized_output_summary,
            "next_action": self.next_action,
            "policy_decision": self.policy_decision,
        }


def _norm(rel: str) -> str:
    return rel.replace("\\", "/").strip().lstrip("./")


def _matches_any(rel: str, globs: Iterable[str]) -> bool:
    for pat in globs:
        p = pat.replace("\\", "/")
        if fnmatch(rel, p):
            return True
        if p.endswith("/**") and (rel == p[:-3] or rel.startswith(p[:-2])):
            return True
    return False


def _all_test_files(repo_root: Path) -> list[str]:
    tests_dir = repo_root / TESTS_DIR
    if not tests_dir.is_dir():
        return []
    out = [
        p.relative_to(repo_root).as_posix()
        for p in tests_dir.rglob("test_*.py")
        if p.is_file()
    ]
    return sorted(set(out))


def _module_dotted(rel_src: str) -> tuple[str, str]:
    """Return (dotted_module, stem) for a src/ai_dev_os/... .py file."""
    rel = _norm(rel_src)
    inner = rel[len("src/") :] if rel.startswith("src/") else rel
    stem = Path(inner).stem
    dotted = inner[:-3].replace("/", ".") if inner.endswith(".py") else inner.replace("/", ".")
    return dotted, stem


def select_related_tests(
    repo_root: Path,
    changed_files: Sequence[str],
    *,
    broad_impact_globs: Sequence[str] | None = None,
) -> TargetedSelection:
    """Deterministically map changed files to the tests that exercise them."""
    root = Path(repo_root).resolve()
    globs = tuple(broad_impact_globs) if broad_impact_globs is not None else DEFAULT_BROAD_IMPACT_GLOBS
    changed = sorted({_norm(c) for c in changed_files if _norm(c)})
    all_tests = _all_test_files(root)
    all_tests_set = set(all_tests)

    sel = TargetedSelection(changed_files=changed)
    selected: set[str] = set()
    rationale: dict[str, set[str]] = {}
    unmapped: list[str] = []
    saw_code = False
    broad = False

    def _add(test_rel: str, why: str) -> None:
        selected.add(test_rel)
        rationale.setdefault(test_rel, set()).add(why)

    for rel in changed:
        if _matches_any(rel, globs):
            broad = True
            saw_code = True
            continue
        if rel.startswith(TESTS_DIR + "/") and Path(rel).name.startswith("test_") and rel.endswith(".py"):
            if rel in all_tests_set:
                _add(rel, "changed_test_file")
            saw_code = True
            continue
        if rel.startswith(PACKAGE_DIR + "/") and rel.endswith(".py"):
            saw_code = True
            dotted, stem = _module_dotted(rel)
            direct = f"{TESTS_DIR}/test_{stem}.py"
            matched = False
            if direct in all_tests_set:
                _add(direct, f"direct_test_for:{stem}")
                matched = True
            import_re = re.compile(
                r"from\s+ai_dev_os\s+import\s+[^\n]*\b" + re.escape(stem) + r"\b"
            )
            for test_rel in all_tests:
                try:
                    text = (root / test_rel).read_text(encoding="utf-8")
                except OSError:
                    continue
                if dotted in text or import_re.search(text):
                    _add(test_rel, f"imports:{dotted}")
                    matched = True
            if not matched:
                unmapped.append(rel)

    sel.unmapped_sources = sorted(set(unmapped))
    if broad:
        sel.broad = True
        sel.reason = "broad_impact"
        sel.selected_tests = list(all_tests)
        sel.rationale = {t: ["broad_impact"] for t in all_tests}
        return sel

    sel.selected_tests = sorted(selected)
    sel.rationale = {k: sorted(v) for k, v in rationale.items()}
    if not saw_code:
        sel.reason = "no_code_impact"
    elif not selected and unmapped:
        sel.reason = "no_related_tests_found"
    elif not selected:
        sel.reason = "no_code_impact"
    else:
        sel.reason = "related"
    return sel


def _parse_pytest_counts(text: str) -> dict[str, int | None]:
    counts: dict[str, int | None] = {
        "tests_passed": None,
        "tests_failed": None,
        "tests_skipped": None,
    }
    for line in reversed(text.splitlines()):
        if "passed" in line or "failed" in line or "no tests ran" in line:
            pm = re.search(r"(\d+)\s+passed", line)
            fm = re.search(r"(\d+)\s+failed", line)
            sm = re.search(r"(\d+)\s+skipped", line)
            if pm or fm or sm:
                counts["tests_passed"] = int(pm.group(1)) if pm else 0
                counts["tests_failed"] = int(fm.group(1)) if fm else 0
                counts["tests_skipped"] = int(sm.group(1)) if sm else 0
                break
            if "no tests ran" in line:
                counts.update(tests_passed=0, tests_failed=0, tests_skipped=0)
                break
    return counts


def run_targeted_tests(
    repo_root: Path,
    selection: TargetedSelection,
    *,
    policy: CIPolicy | None = None,
    fallback_full: bool = False,
) -> TargetedTestRun:
    """Execute the selected tests via the sanitized argv-only CI runner."""
    root = Path(repo_root).resolve()
    pol = policy or load_ci_policy(root / "config" / "ci_policy.yaml")
    run = TargetedTestRun(
        repository_identity=str(root),
        selection=selection.to_dict(),
        started_at=utc_now_iso(),
    )
    try:
        from .git_safety import inspect_repo

        run.starting_commit = inspect_repo(root).head or ""
    except Exception:  # noqa: BLE001
        run.starting_commit = ""

    targets = list(selection.selected_tests)
    ran_full = False
    if not targets:
        if fallback_full:
            ran_full = True
            argv = [sys.executable, "-m", "pytest", "-q"]
        else:
            run.finished_at = utc_now_iso()
            run.final_verdict = CIVerdict.PASS_WITH_NOTES.value
            run.next_action = (
                "no related tests selected; run full `ci-check` before completion"
            )
            run.sanitized_output_summary = f"selection reason={selection.reason}"
            return run
    else:
        # Defense-in-depth: only allow real files under tests/ as targets.
        safe_targets: list[str] = []
        for t in targets:
            tn = _norm(t)
            if tn.startswith(TESTS_DIR + "/") and (root / tn).is_file():
                safe_targets.append(tn)
        if not safe_targets:
            # Specific tests were requested but none survived safety filtering.
            # Fail closed: never silently fall through to running the whole suite.
            run.finished_at = utc_now_iso()
            run.final_verdict = CIVerdict.FAIL.value
            run.failure_class = "command_rejected"
            run.policy_decision = "deny"
            run.sanitized_output_summary = "no valid test targets after safety filtering"
            run.next_action = "verify selected test paths are real files under tests/"
            return run
        argv = [sys.executable, "-m", "pytest", "-q", *safe_targets]

    run.ran_full_suite = ran_full
    run.command_identity = "python -m pytest -q " + ("<full>" if ran_full else "<targeted>")
    t0 = time.perf_counter()
    try:
        cmd = run_ci_command(
            argv,
            cwd=root,
            timeout=pol.clamp_timeout(None, default=pol.pytest_timeout_seconds),
            output_limit_bytes=pol.output_limit_bytes,
        )
    except CICommandError as exc:
        run.finished_at = utc_now_iso()
        run.duration_seconds = round(time.perf_counter() - t0, 4)
        run.final_verdict = CIVerdict.FAIL.value
        run.failure_class = "command_rejected"
        run.policy_decision = "deny"
        run.sanitized_output_summary = str(exc)
        run.next_action = "reject unsafe targeted command"
        return run

    text = (cmd.stdout or "") + "\n" + (cmd.stderr or "")
    counts = _parse_pytest_counts(text)
    run.tests_passed = counts["tests_passed"]
    run.tests_failed = counts["tests_failed"]
    run.tests_skipped = counts["tests_skipped"]
    run.exit_status = cmd.exit_code
    run.timeout_status = cmd.timed_out
    run.truncation_status = cmd.truncated
    run.finished_at = utc_now_iso()
    run.duration_seconds = round(time.perf_counter() - t0, 4)
    from .ci_stages import redact_tail

    run.sanitized_output_summary = redact_tail(text) or "pytest ok"
    if cmd.timed_out:
        run.final_verdict = CIVerdict.FAIL.value
        run.failure_class = "timeout"
        run.policy_decision = "deny"
        run.next_action = "targeted tests timed out; investigate"
    elif cmd.exit_code != 0:
        run.final_verdict = CIVerdict.FAIL.value
        run.failure_class = "tests_failed"
        run.policy_decision = "deny"
        run.next_action = "fix failing targeted tests, then run full ci-check"
    else:
        run.final_verdict = (
            CIVerdict.PASS.value if ran_full else CIVerdict.PASS_WITH_NOTES.value
        )
        run.next_action = (
            "targeted tests pass; run full `ci-check` before marking complete"
            if not ran_full
            else "full suite passed via targeted fallback"
        )
    return run


def exit_code_for_targeted_run(run: TargetedTestRun) -> int:
    if run.final_verdict in {CIVerdict.PASS.value, CIVerdict.PASS_WITH_NOTES.value}:
        return 0
    return 1
