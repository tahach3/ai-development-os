"""Constitutional Court — deterministic Article XIV preflight (no LLM, no network)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from .fingerprints import fingerprint, fingerprint_plan, fingerprint_task
from .models import (
    ApprovalRequirement,
    Complexity,
    Plan,
    RiskLevel,
    Task,
    TaskType,
    utc_now_iso,
)
from .project_registry import EQUITIFY_SENTINELS

COURT_SCHEMA_VERSION = "14.1"
COURT_RULES_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({COURT_SCHEMA_VERSION})
SUPPORTED_RULES_VERSIONS = frozenset({COURT_RULES_VERSION})

HIGH_RISK_LEVELS = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})

# §2.6 allowlisted metric tokens
METRIC_ALLOWLIST = frozenset(
    {
        "tests_pass",
        "ci_check_ok",
        "repair_count",
        "latency",
        "cost",
        "human_corrections",
        "accepted_outputs",
        "failures",
        "behavioral_report",
    }
)

# §2.5 P-004 denylist phrases (conservative)
CHAT_ONLY_STEP_PHRASES = (
    "ask the model",
    "ask the llm",
    "paste into chat",
    "chat paste",
    "ask chatgpt",
    "ask claude in chat",
)

# §2.2 constitution / locked-domain needles (path + intent text)
AUDIT_WIPE_NEEDLES = (
    "workspace/audit",
    "/audit",
    "provider_executions",
    "wipe audit",
    "delete audit",
    "rewrite audit",
)

SECRET_INTENT_NEEDLES = (
    "reading_env_secrets",
    "read env secrets",
    "reading .env",
    "storing_api_keys",
    "store api keys",
    "storing api keys",
    "executing_generated_code",
    "execute generated",
    "executing generated provider",
)

MEMORY_AUTO_NEEDLES = (
    "auto_activate_self_improvement",
    "auto-activate learning",
    "auto activate learning",
    "auto-approve memory",
    "auto approve memory",
    "wire memory into orchestration",
    "wires memory into orchestration",
    "memory into orchestration",
)

SELF_REWRITE_NEEDLES = (
    "rewrite constitution",
    "self-rewrite os",
    "self rewrite os",
    "rewrite core gates",
    "amend constitution without",
)

LIVE_PROVIDER_NEEDLES = (
    "paid_llm_api_calls",
    "paid llm",
    "live provider",
    "live model",
    "network model",
    "round 4d2",
    "4d2",
)

EQUITIFY_CROSS_NEEDLES = (
    "equitify adapter",
    "cross-project merge",
    "cross project merge",
    "equitify_integration",
)

# §5.1 amendment / gate scope paths (normalized prefix/exact)
AMENDMENT_SCOPE_PATHS = (
    "docs/constitution.md",
    "src/ai_dev_os/approval.py",
    "src/ai_dev_os/lifecycle_gates.py",
    "src/ai_dev_os/safe_policy.py",
    "src/ai_dev_os/provider_policy.py",
    "src/ai_dev_os/provider_runner.py",
    "src/ai_dev_os/providers/",
)

GITHUB_WORKFLOW_NEEDLES = (
    ".github/workflows/",
    "github/workflows",
)

DEFAULT_SAFETY_CRITICAL_PREFIXES = (
    "config/",
    "schemas/",
    ".github/workflows/",
    "src/ai_dev_os/safe_policy.py",
    "src/ai_dev_os/approval.py",
    "src/ai_dev_os/lifecycle_gates.py",
    "src/ai_dev_os/provider_policy.py",
    "src/ai_dev_os/git_safety.py",
    "src/ai_dev_os/project_registry.py",
    "src/ai_dev_os/ci_config.py",
    "src/ai_dev_os/ci_engine.py",
    "src/ai_dev_os/constitutional_court.py",
)

# Policy prohibitions that high/critical plans must list (substring match).
DEFAULT_REQUIRED_PROHIBITIONS = (
    "equitify_integration",
    "paid_llm_api_calls",
    "executing_generated_code",
    "auto_approve_high_risk",
    "auto_activate_self_improvement",
    "reading_env_secrets",
    "storing_api_keys",
)

_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$", re.IGNORECASE)


class CourtVerdict(str, Enum):
    PASS = "pass"
    PASS_WITH_NOTES = "pass_with_notes"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    ADVISORY_ONLY = "advisory_only"


class CourtCheckId(str, Enum):
    CONSTITUTION_VIOLATION = "constitution_violation"
    SAFETY_REGRESSION = "safety_regression"
    RISK_INCREASE = "risk_increase"
    REPRODUCIBILITY = "reproducibility"
    MEASURABILITY = "measurability"


class CourtCheckResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CourtFindingSeverity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NOTE = "note"


class CourtFailureClass(str, Enum):
    NONE = "none"
    CONSTITUTION_VIOLATION = "constitution_violation"
    SAFETY_REGRESSION = "safety_regression"
    RISK_UNDERCLASSIFIED = "risk_underclassified"
    RISK_INCREASE = "risk_increase"
    NOT_REPRODUCIBLE = "not_reproducible"
    NOT_MEASURABLE = "not_measurable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SELF_REVIEW_FORBIDDEN = "self_review_forbidden"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    UNSUPPORTED_RULES_VERSION = "unsupported_rules_version"
    EQUITIFY_BOUNDARY = "equitify_boundary"
    LIVE_PROVIDER_LOCKED = "live_provider_locked"
    REGISTRY_INCOMPATIBLE = "registry_incompatible"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    INTERNAL_ERROR = "internal_error"


@dataclass
class CourtFinding:
    check_id: CourtCheckId
    rule_id: str
    severity: CourtFindingSeverity
    summary: str
    evidence_refs: list[str] = field(default_factory=list)
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id.value,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CourtFinding:
        return cls(
            check_id=CourtCheckId(data["check_id"]),
            rule_id=str(data["rule_id"]),
            severity=CourtFindingSeverity(data["severity"]),
            summary=str(data["summary"]),
            evidence_refs=list(data.get("evidence_refs") or []),
            path=data.get("path"),
        )


@dataclass
class CourtCheckOutcome:
    check_id: CourtCheckId
    result: CourtCheckResult
    findings: list[CourtFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id.value,
            "result": self.result.value,
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CourtCheckOutcome:
        return cls(
            check_id=CourtCheckId(data["check_id"]),
            result=CourtCheckResult(data["result"]),
            findings=[CourtFinding.from_dict(f) for f in (data.get("findings") or [])],
        )


@dataclass
class CourtEvidenceEnvelope:
    schema_version: str = COURT_SCHEMA_VERSION
    user_authorized_equitify: bool = False
    user_authorized_4d2: bool = False
    safety_impact_declared: bool = False
    weakens_authz: bool = False
    disables_fail_closed: bool = False
    enables_shell_true: bool = False
    removes_output_caps: bool = False
    auto_approve_high_risk: bool = False
    accept_unresolved: bool = False
    requires_network: bool = False
    requires_live_model: bool = False
    commands_are_argv_only: bool = True
    vuln_db_queried: bool = False
    metrics_declared: list[str] = field(default_factory=list)
    fixture_or_seed_refs: list[str] = field(default_factory=list)
    safety_critical_paths_touched: list[str] = field(default_factory=list)
    authorization_note: str | None = None
    human_review: bool = False
    prior_plan_risk_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "user_authorized_equitify": self.user_authorized_equitify,
            "user_authorized_4d2": self.user_authorized_4d2,
            "safety_impact_declared": self.safety_impact_declared,
            "weakens_authz": self.weakens_authz,
            "disables_fail_closed": self.disables_fail_closed,
            "enables_shell_true": self.enables_shell_true,
            "removes_output_caps": self.removes_output_caps,
            "auto_approve_high_risk": self.auto_approve_high_risk,
            "accept_unresolved": self.accept_unresolved,
            "requires_network": self.requires_network,
            "requires_live_model": self.requires_live_model,
            "commands_are_argv_only": self.commands_are_argv_only,
            "vuln_db_queried": self.vuln_db_queried,
            "metrics_declared": list(self.metrics_declared),
            "fixture_or_seed_refs": list(self.fixture_or_seed_refs),
            "safety_critical_paths_touched": list(self.safety_critical_paths_touched),
            "authorization_note": self.authorization_note,
            "human_review": self.human_review,
            "prior_plan_risk_level": self.prior_plan_risk_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CourtEvidenceEnvelope:
        if not data:
            return cls()
        return cls(
            schema_version=str(data.get("schema_version") or COURT_SCHEMA_VERSION),
            user_authorized_equitify=bool(data.get("user_authorized_equitify", False)),
            user_authorized_4d2=bool(data.get("user_authorized_4d2", False)),
            safety_impact_declared=bool(data.get("safety_impact_declared", False)),
            weakens_authz=bool(data.get("weakens_authz", False)),
            disables_fail_closed=bool(data.get("disables_fail_closed", False)),
            enables_shell_true=bool(data.get("enables_shell_true", False)),
            removes_output_caps=bool(data.get("removes_output_caps", False)),
            auto_approve_high_risk=bool(data.get("auto_approve_high_risk", False)),
            accept_unresolved=bool(data.get("accept_unresolved", False)),
            requires_network=bool(data.get("requires_network", False)),
            requires_live_model=bool(data.get("requires_live_model", False)),
            commands_are_argv_only=bool(data.get("commands_are_argv_only", True)),
            vuln_db_queried=bool(data.get("vuln_db_queried", False)),
            metrics_declared=[str(x) for x in (data.get("metrics_declared") or [])],
            fixture_or_seed_refs=[str(x) for x in (data.get("fixture_or_seed_refs") or [])],
            safety_critical_paths_touched=[
                str(x) for x in (data.get("safety_critical_paths_touched") or [])
            ],
            authorization_note=data.get("authorization_note"),
            human_review=bool(data.get("human_review", False)),
            prior_plan_risk_level=(
                str(data["prior_plan_risk_level"])
                if data.get("prior_plan_risk_level") is not None
                else None
            ),
        )


@dataclass
class CourtRecord:
    schema_version: str
    court_rules_version: str
    record_id: str
    task_id: str
    plan_id: str
    project_id: str
    required: bool
    evaluated_by: str
    evaluated_at: str
    starting_commit: str
    verdict: CourtVerdict
    checks: list[CourtCheckOutcome]
    findings: list[CourtFinding]
    failure_classes: list[str]
    notes: str | None
    task_fingerprint: str
    plan_fingerprint: str
    evidence_fingerprint: str
    content_fingerprint: str
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "court_rules_version": self.court_rules_version,
            "record_id": self.record_id,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "required": self.required,
            "evaluated_by": self.evaluated_by,
            "evaluated_at": self.evaluated_at,
            "starting_commit": self.starting_commit,
            "verdict": self.verdict.value,
            "checks": [c.to_dict() for c in self.checks],
            "findings": [f.to_dict() for f in self.findings],
            "failure_classes": list(self.failure_classes),
            "notes": self.notes,
            "task_fingerprint": self.task_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "content_fingerprint": self.content_fingerprint,
            "next_action": self.next_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CourtRecord:
        return cls(
            schema_version=str(data["schema_version"]),
            court_rules_version=str(data["court_rules_version"]),
            record_id=str(data["record_id"]),
            task_id=str(data["task_id"]),
            plan_id=str(data["plan_id"]),
            project_id=str(data["project_id"]),
            required=bool(data["required"]),
            evaluated_by=str(data["evaluated_by"]),
            evaluated_at=str(data["evaluated_at"]),
            starting_commit=str(data["starting_commit"]),
            verdict=CourtVerdict(data["verdict"]),
            checks=[CourtCheckOutcome.from_dict(c) for c in (data.get("checks") or [])],
            findings=[CourtFinding.from_dict(f) for f in (data.get("findings") or [])],
            failure_classes=[str(x) for x in (data.get("failure_classes") or [])],
            notes=data.get("notes"),
            task_fingerprint=str(data["task_fingerprint"]),
            plan_fingerprint=str(data["plan_fingerprint"]),
            evidence_fingerprint=str(data["evidence_fingerprint"]),
            content_fingerprint=str(data["content_fingerprint"]),
            next_action=str(data.get("next_action") or ""),
        )


def normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("./")


def path_has_prefix(path: str, prefix: str) -> bool:
    p = normalize_rel_path(path).lower()
    r = normalize_rel_path(prefix).lower().rstrip("/")
    if not r:
        return False
    return p == r or p.startswith(r + "/") or p.startswith(r)


def _blob(*parts: str) -> str:
    return "\n".join(str(p).lower().replace("\\", "/") for p in parts if p)


def _contains_any(haystack: str, needles: Sequence[str]) -> str | None:
    low = haystack.lower().replace("\\", "/")
    for needle in needles:
        n = needle.lower().replace("\\", "/").strip()
        if n and n in low:
            return needle
    return None


def _finding(
    check_id: CourtCheckId,
    rule_id: str,
    summary: str,
    *,
    severity: CourtFindingSeverity = CourtFindingSeverity.BLOCKER,
    evidence_refs: list[str] | None = None,
    path: str | None = None,
) -> CourtFinding:
    return CourtFinding(
        check_id=check_id,
        rule_id=rule_id,
        severity=severity,
        summary=summary,
        evidence_refs=list(evidence_refs or []),
        path=path,
    )


def _is_insufficient_finding(finding: CourtFinding) -> bool:
    return finding.rule_id.endswith(".IE") or "insufficient" in finding.summary.lower()


def _outcome(
    check_id: CourtCheckId, findings: list[CourtFinding]
) -> CourtCheckOutcome:
    if not findings:
        return CourtCheckOutcome(check_id=check_id, result=CourtCheckResult.PASS, findings=[])
    blockers = [
        f
        for f in findings
        if f.severity in (CourtFindingSeverity.BLOCKER, CourtFindingSeverity.MAJOR)
    ]
    if not blockers:
        return CourtCheckOutcome(
            check_id=check_id, result=CourtCheckResult.PASS, findings=findings
        )
    if all(_is_insufficient_finding(f) for f in blockers):
        return CourtCheckOutcome(
            check_id=check_id,
            result=CourtCheckResult.INSUFFICIENT_EVIDENCE,
            findings=findings,
        )
    return CourtCheckOutcome(
        check_id=check_id, result=CourtCheckResult.FAIL, findings=findings
    )


def _ie(
    check_id: CourtCheckId,
    rule_id: str,
    summary: str,
    *,
    evidence_refs: list[str] | None = None,
    path: str | None = None,
) -> CourtFinding:
    return _finding(
        check_id,
        rule_id if rule_id.endswith(".IE") else f"{rule_id}.IE",
        summary if "insufficient" in summary.lower() else f"insufficient evidence: {summary}",
        severity=CourtFindingSeverity.BLOCKER,
        evidence_refs=evidence_refs,
        path=path,
    )


def collect_scope_paths(task: Task, plan: Plan, evidence: CourtEvidenceEnvelope) -> list[str]:
    paths: list[str] = []
    for p in plan.files_expected_to_change:
        paths.append(normalize_rel_path(p))
    for p in task.allowed_paths:
        paths.append(normalize_rel_path(p))
    for p in evidence.safety_critical_paths_touched:
        paths.append(normalize_rel_path(p))
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def safety_critical_hits(
    paths: Sequence[str], prefixes: Sequence[str] | None = None
) -> list[str]:
    prefs = tuple(prefixes or DEFAULT_SAFETY_CRITICAL_PREFIXES)
    hits: list[str] = []
    for path in paths:
        for pref in prefs:
            if path_has_prefix(path, pref):
                hits.append(path)
                break
    return hits


def equitify_path_hits(paths: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        low = path.lower().replace("\\", "/")
        for sentinel in EQUITIFY_SENTINELS:
            if sentinel in low:
                hits.append(path)
                break
    return hits


def intent_blob(task: Task, plan: Plan) -> str:
    """Affirmative declared intent — excludes prohibited_actions (those are denials)."""
    return _blob(
        plan.objective,
        *plan.scope,
        *plan.implementation_steps,
        *plan.risks,
        *plan.unresolved_questions,
        task.description,
        task.title,
        *task.prohibited_paths,
    )


def implies_high_signals(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    *,
    safety_prefixes: Sequence[str] | None = None,
) -> list[str]:
    """Return human-readable signals that imply ≥ high risk."""
    signals: list[str] = []
    paths = collect_scope_paths(task, plan, evidence)
    if safety_critical_hits(paths, safety_prefixes):
        signals.append("safety_critical_paths")
    if equitify_path_hits(paths):
        signals.append("equitify_paths")
    blob = intent_blob(task, plan)
    if evidence.requires_live_model or evidence.requires_network:
        signals.append("live_or_network_required")
    if _contains_any(blob, LIVE_PROVIDER_NEEDLES):
        signals.append("live_provider_intent")
    if _contains_any(blob, EQUITIFY_CROSS_NEEDLES) or _contains_any(
        blob, EQUITIFY_SENTINELS
    ):
        signals.append("equitify_intent")
    # Schema / policy / constitution amendment scope
    for path in paths:
        pl = path.lower()
        if pl.startswith("config/") and "policy" in pl:
            signals.append("policy_config_change")
            break
        if any(path_has_prefix(path, a) for a in AMENDMENT_SCOPE_PATHS):
            signals.append("amendment_scope_path")
            break
        if pl.endswith(".yaml") or pl.endswith(".yml"):
            if "schema" in pl or pl.startswith("schemas/"):
                signals.append("schema_change")
                break
    if task.task_type is TaskType.ARCHITECTURE:
        signals.append("architecture_task")
    if any("rewrite core lifecycle" in s.lower() for s in plan.scope):
        signals.append("rewrite_core_lifecycle")
    return signals


def is_major_change(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope | None = None,
    *,
    safety_prefixes: Sequence[str] | None = None,
) -> bool:
    """§5.1 operational definition of major change (Court required)."""
    ev = evidence or CourtEvidenceEnvelope()
    if task.risk_level in HIGH_RISK_LEVELS or plan.risk_level in HIGH_RISK_LEVELS:
        return True
    if task.complexity is Complexity.HIGH_RISK:
        return True
    paths = collect_scope_paths(task, plan, ev)
    if safety_critical_hits(paths, safety_prefixes):
        return True
    if implies_high_signals(task, plan, ev, safety_prefixes=safety_prefixes):
        # Locked-domain / amendment / architecture signals make it major.
        return True
    return False


def _risk_rank(level: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }[level]


def check_constitution_violation(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    *,
    required: bool,
) -> CourtCheckOutcome:
    cid = CourtCheckId.CONSTITUTION_VIOLATION
    findings: list[CourtFinding] = []
    paths = collect_scope_paths(task, plan, evidence)
    blob = intent_blob(task, plan)
    path_blob = _blob(*paths)

    # C-GOV-001: self-approval / removes human approval for high/critical
    if plan.risk_level in HIGH_RISK_LEVELS or task.risk_level in HIGH_RISK_LEVELS:
        if plan.approval_requirement is ApprovalRequirement.NONE:
            findings.append(
                _finding(
                    cid,
                    "C-GOV-001",
                    "high/critical plan claims approval_requirement=none (removes human approval)",
                    evidence_refs=["plan.approval_requirement"],
                )
            )
        if _contains_any(blob, ("self-approval", "self approval", "auto_approve_high_risk")):
            if "auto_approve" in blob or "self-approval" in blob or "self approval" in blob:
                findings.append(
                    _finding(
                        cid,
                        "C-GOV-001",
                        "plan claims self-approval or auto-approve for high/critical",
                        evidence_refs=["plan.objective", "plan.scope"],
                    )
                )

    # C-GOV-002: audit history wipe paths
    hit = _contains_any(path_blob + "\n" + blob, AUDIT_WIPE_NEEDLES)
    if hit:
        findings.append(
            _finding(
                cid,
                "C-GOV-002",
                f"scope includes audit-history wipe/rewrite needle {hit!r}",
                evidence_refs=["plan.files_expected_to_change"],
                path=hit,
            )
        )

    # C-SEC-001: Equitify sentinels without authorization
    eq_hits = equitify_path_hits(paths)
    eq_intent = _contains_any(blob, EQUITIFY_SENTINELS) or _contains_any(
        blob, EQUITIFY_CROSS_NEEDLES
    )
    if (eq_hits or eq_intent) and not evidence.user_authorized_equitify:
        findings.append(
            _finding(
                cid,
                "C-SEC-001",
                "Equitify sentinel/path in scope without user_authorized_equitify",
                evidence_refs=["evidence.user_authorized_equitify", "plan.files_expected_to_change"],
                path=eq_hits[0] if eq_hits else None,
            )
        )

    # C-SEC-002: live/paid provider without 4D2 auth
    live_hit = _contains_any(blob, LIVE_PROVIDER_NEEDLES)
    if (
        evidence.requires_live_model
        or evidence.requires_network
        or live_hit
    ) and not evidence.user_authorized_4d2:
        findings.append(
            _finding(
                cid,
                "C-SEC-002",
                "paid/live provider or network model intent without user_authorized_4d2",
                evidence_refs=["evidence.user_authorized_4d2", "evidence.requires_live_model"],
            )
        )

    # C-SEC-003: secrets / execute generated
    sec_hit = _contains_any(blob, SECRET_INTENT_NEEDLES)
    if sec_hit:
        findings.append(
            _finding(
                cid,
                "C-SEC-003",
                f"declared intent includes forbidden secret/exec needle {sec_hit!r}",
                evidence_refs=["plan.objective", "plan.scope"],
            )
        )

    # C-MEM-001: memory auto-activation
    mem_hit = _contains_any(blob, MEMORY_AUTO_NEEDLES)
    if mem_hit:
        findings.append(
            _finding(
                cid,
                "C-MEM-001",
                f"declared intent auto-activates learning/memory wiring ({mem_hit!r})",
                evidence_refs=["plan.scope", "plan.implementation_steps"],
            )
        )

    # C-BIZ-001: cross-project / Equitify adapter
    biz_hit = _contains_any(blob, EQUITIFY_CROSS_NEEDLES)
    if biz_hit and not evidence.user_authorized_equitify:
        findings.append(
            _finding(
                cid,
                "C-BIZ-001",
                f"cross-project/Equitify adapter without authorization ({biz_hit!r})",
                evidence_refs=["evidence.user_authorized_equitify"],
            )
        )

    # C-EVO-001: self-rewrite constitution/core gates
    evo_hit = _contains_any(blob, SELF_REWRITE_NEEDLES)
    if evo_hit:
        findings.append(
            _finding(
                cid,
                "C-EVO-001",
                f"declared self-rewrite of constitution/core gates ({evo_hit!r})",
                evidence_refs=["plan.objective"],
            )
        )

    # C-ENG-001: major missing engineering fields (overlap Q4/Q5)
    if required:
        missing: list[str] = []
        if not plan.testing_plan:
            missing.append("testing_plan")
        if not plan.rollback_or_recovery_plan:
            missing.append("rollback_or_recovery_plan")
        if not any("doc" in s.lower() for s in plan.scope + plan.implementation_steps):
            # docs intent: note only if completely absent from engineering fields —
            # treat empty testing/rollback as the hard fail; docs as major note via C-ENG
            pass
        if missing:
            findings.append(
                _ie(
                    cid,
                    "C-ENG-001",
                    f"major-change plan missing required engineering fields: {', '.join(missing)}",
                    evidence_refs=[f"plan.{m}" for m in missing],
                )
            )

    return _outcome(cid, findings)


def check_safety_regression(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    *,
    required: bool,
    safety_prefixes: Sequence[str] | None = None,
    required_prohibitions: Sequence[str] | None = None,
) -> CourtCheckOutcome:
    cid = CourtCheckId.SAFETY_REGRESSION
    findings: list[CourtFinding] = []
    paths = collect_scope_paths(task, plan, evidence)
    crit = safety_critical_hits(paths, safety_prefixes)

    # S-001
    if crit and not evidence.safety_impact_declared:
        if required:
            findings.append(
                _ie(
                    cid,
                    "S-001",
                    "safety-critical paths in scope without safety_impact_declared",
                    evidence_refs=["evidence.safety_impact_declared"],
                    path=crit[0],
                )
            )
        else:
            findings.append(
                _finding(
                    cid,
                    "S-001",
                    "safety-critical paths in scope without safety_impact_declared",
                    evidence_refs=["evidence.safety_impact_declared"],
                    path=crit[0],
                )
            )

    # S-002
    if evidence.weakens_authz:
        findings.append(
            _finding(
                cid,
                "S-002",
                "evidence.weakens_authz is true",
                evidence_refs=["evidence.weakens_authz"],
            )
        )
    if evidence.disables_fail_closed:
        findings.append(
            _finding(
                cid,
                "S-002",
                "evidence.disables_fail_closed is true",
                evidence_refs=["evidence.disables_fail_closed"],
            )
        )
    if evidence.auto_approve_high_risk:
        findings.append(
            _finding(
                cid,
                "S-002",
                "evidence.auto_approve_high_risk is true",
                evidence_refs=["evidence.auto_approve_high_risk"],
            )
        )

    # S-003: high/critical must list required prohibitions from policy
    if plan.risk_level in HIGH_RISK_LEVELS or task.risk_level in HIGH_RISK_LEVELS:
        req = tuple(required_prohibitions or DEFAULT_REQUIRED_PROHIBITIONS)
        joined = _blob(*plan.prohibited_actions)
        # Also accept underscore/space variants and common aliases
        aliases = {
            "equitify_integration": ("equitify", "equitify_integration"),
            "paid_llm_api_calls": ("paid_llm", "paid llm", "network", "paid_llm_api_calls"),
            "executing_generated_code": (
                "executing_generated",
                "execute generated",
                "generated code",
                "executing_generated_code",
            ),
            "auto_approve_high_risk": ("auto_approve", "auto-approve", "auto_approve_high_risk"),
            "auto_activate_self_improvement": (
                "self_improvement",
                "self-improvement",
                "auto_activate_self_improvement",
            ),
            "reading_env_secrets": (
                "reading_env",
                "env secrets",
                ".env",
                "reading_env_secrets",
            ),
            "storing_api_keys": ("api keys", "api_keys", "storing_api_keys"),
        }
        missing_props: list[str] = []
        for prop in req:
            variants = aliases.get(prop, (prop, prop.replace("_", " ")))
            if not any(v.lower() in joined for v in variants):
                missing_props.append(prop)
        if missing_props:
            findings.append(
                _finding(
                    cid,
                    "S-003",
                    "high/critical plan prohibited_actions missing required policy prohibitions: "
                    + ", ".join(missing_props),
                    evidence_refs=["plan.prohibited_actions"],
                )
            )

    # S-004: GitHub workflow permissions/secrets without human_review
    gh_paths = [
        p
        for p in paths
        if _contains_any(p, GITHUB_WORKFLOW_NEEDLES)
        or "secrets" in p.lower()
        and ".github" in p.lower()
    ]
    if gh_paths and not evidence.human_review:
        findings.append(
            _finding(
                cid,
                "S-004",
                "touches GitHub workflow/secrets patterns without human_review evidence",
                evidence_refs=["evidence.human_review"],
                path=gh_paths[0],
            )
        )

    return _outcome(cid, findings)


def check_risk_increase(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    *,
    required: bool,
    safety_prefixes: Sequence[str] | None = None,
) -> CourtCheckOutcome:
    cid = CourtCheckId.RISK_INCREASE
    findings: list[CourtFinding] = []
    signals = implies_high_signals(task, plan, evidence, safety_prefixes=safety_prefixes)
    declared = plan.risk_level
    if task.risk_level in HIGH_RISK_LEVELS:
        # plan understates task checked in R-003
        pass

    # R-001 under-classification
    if signals and declared in (RiskLevel.LOW, RiskLevel.MEDIUM):
        findings.append(
            _finding(
                cid,
                "R-001",
                f"signals imply ≥ high ({', '.join(signals)}) but declared risk is {declared.value}",
                evidence_refs=["plan.risk_level", "plan.files_expected_to_change"],
            )
        )

    # R-002
    if (
        plan.risk_level in HIGH_RISK_LEVELS or task.risk_level in HIGH_RISK_LEVELS
    ) and plan.approval_requirement is ApprovalRequirement.NONE:
        findings.append(
            _finding(
                cid,
                "R-002",
                "risk_level high/critical but approval_requirement is none",
                evidence_refs=["plan.approval_requirement"],
            )
        )

    # R-003 plan understates task
    if _risk_rank(plan.risk_level) < _risk_rank(task.risk_level):
        findings.append(
            _finding(
                cid,
                "R-003",
                f"plan risk {plan.risk_level.value} < task risk {task.risk_level.value}",
                evidence_refs=["plan.risk_level", "task.risk_level"],
            )
        )

    # R-004
    if plan.risk_level in HIGH_RISK_LEVELS or task.risk_level in HIGH_RISK_LEVELS:
        if not plan.risks or not plan.rollback_or_recovery_plan:
            findings.append(
                _ie(
                    cid,
                    "R-004",
                    "high/critical without non-empty risks[] and rollback_or_recovery_plan[]",
                    evidence_refs=["plan.risks", "plan.rollback_or_recovery_plan"],
                )
            )

    # R-005
    if (
        (plan.risk_level in HIGH_RISK_LEVELS or task.risk_level in HIGH_RISK_LEVELS)
        and plan.unresolved_questions
        and not evidence.accept_unresolved
    ):
        if required:
            findings.append(
                _finding(
                    cid,
                    "R-005",
                    "unresolved questions on high/critical without accept_unresolved",
                    evidence_refs=["evidence.accept_unresolved", "plan.unresolved_questions"],
                )
            )

    return _outcome(cid, findings)


def check_reproducibility(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    *,
    required: bool,
) -> CourtCheckOutcome:
    cid = CourtCheckId.REPRODUCIBILITY
    findings: list[CourtFinding] = []

    # P-001
    commit = (plan.starting_commit or "").strip()
    if not commit or not _COMMIT_RE.match(commit):
        findings.append(
            _ie(
                cid,
                "P-001",
                "missing/blank or malformed starting_commit",
                evidence_refs=["plan.starting_commit"],
            )
        )

    # P-002
    if required and (not plan.implementation_steps or not plan.testing_plan):
        findings.append(
            _ie(
                cid,
                "P-002",
                "major change with empty implementation_steps or empty testing_plan",
                evidence_refs=["plan.implementation_steps", "plan.testing_plan"],
            )
        )

    # P-003
    if (evidence.requires_network or evidence.requires_live_model) and not evidence.user_authorized_4d2:
        findings.append(
            _finding(
                cid,
                "P-003",
                "requires_network/requires_live_model true while 4D2 unauthorized",
                evidence_refs=["evidence.requires_live_model", "evidence.user_authorized_4d2"],
            )
        )

    # P-004
    for step in plan.implementation_steps:
        hit = _contains_any(step, CHAT_ONLY_STEP_PHRASES)
        if hit:
            findings.append(
                _finding(
                    cid,
                    "P-004",
                    f"step references chat-only denylist phrase {hit!r}",
                    evidence_refs=["plan.implementation_steps"],
                )
            )

    return _outcome(cid, findings)


def check_measurability(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    *,
    required: bool,
) -> CourtCheckOutcome:
    cid = CourtCheckId.MEASURABILITY
    findings: list[CourtFinding] = []

    # M-001
    if required and not task.acceptance_criteria:
        findings.append(
            _ie(
                cid,
                "M-001",
                "major change with empty task acceptance_criteria",
                evidence_refs=["task.acceptance_criteria"],
            )
        )

    # M-002
    if required and not plan.testing_plan:
        findings.append(
            _ie(
                cid,
                "M-002",
                "empty testing_plan (measurement gap)",
                evidence_refs=["plan.testing_plan"],
            )
        )

    # M-003
    metrics = [m for m in evidence.metrics_declared if m in METRIC_ALLOWLIST]
    test_blob = _blob(*plan.testing_plan)
    mapped = any(
        token.replace("_", " ") in test_blob or token in test_blob
        for token in METRIC_ALLOWLIST
    ) or any(
        tok in test_blob
        for tok in ("pytest", "tests pass", "ci-check", "ci_check", "behavioral")
    )
    if required and not metrics and not mapped:
        findings.append(
            _ie(
                cid,
                "M-003",
                "no metrics_declared and no mapping from testing_plan to allowlisted metrics",
                evidence_refs=["evidence.metrics_declared", "plan.testing_plan"],
            )
        )

    # M-004
    claims_vuln = any(
        "vulnerability_scan" in m.lower() or "vuln" in m.lower()
        for m in evidence.metrics_declared
    ) or "vulnerability_scan" in test_blob
    if claims_vuln and not evidence.vuln_db_queried:
        findings.append(
            _finding(
                cid,
                "M-004",
                "claims vulnerability_scan success without vuln_db_queried",
                evidence_refs=["evidence.vuln_db_queried"],
            )
        )

    return _outcome(cid, findings)


def _failure_classes_for(
    checks: list[CourtCheckOutcome], evidence: CourtEvidenceEnvelope, paths: Sequence[str]
) -> list[str]:
    classes: list[str] = []
    for outcome in checks:
        if outcome.result is CourtCheckResult.PASS:
            continue
        if outcome.result is CourtCheckResult.INSUFFICIENT_EVIDENCE:
            classes.append(CourtFailureClass.INSUFFICIENT_EVIDENCE.value)
        cid = outcome.check_id
        if cid is CourtCheckId.CONSTITUTION_VIOLATION:
            rule_ids = {f.rule_id.split(".")[0] for f in outcome.findings}
            if "C-SEC-001" in rule_ids or "C-BIZ-001" in rule_ids or equitify_path_hits(paths):
                classes.append(CourtFailureClass.EQUITIFY_BOUNDARY.value)
            if "C-SEC-002" in rule_ids or evidence.requires_live_model:
                classes.append(CourtFailureClass.LIVE_PROVIDER_LOCKED.value)
            classes.append(CourtFailureClass.CONSTITUTION_VIOLATION.value)
        elif cid is CourtCheckId.SAFETY_REGRESSION:
            classes.append(CourtFailureClass.SAFETY_REGRESSION.value)
        elif cid is CourtCheckId.RISK_INCREASE:
            if any(f.rule_id.startswith("R-001") for f in outcome.findings):
                classes.append(CourtFailureClass.RISK_UNDERCLASSIFIED.value)
            classes.append(CourtFailureClass.RISK_INCREASE.value)
        elif cid is CourtCheckId.REPRODUCIBILITY:
            if any(f.rule_id.startswith("P-003") for f in outcome.findings):
                classes.append(CourtFailureClass.LIVE_PROVIDER_LOCKED.value)
            classes.append(CourtFailureClass.NOT_REPRODUCIBLE.value)
        elif cid is CourtCheckId.MEASURABILITY:
            classes.append(CourtFailureClass.NOT_MEASURABLE.value)
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in classes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def court_record_stable_payload(record_dict: dict[str, Any]) -> dict[str, Any]:
    """Fingerprint-stable Court payload (excludes volatile evaluated_at / content_fp)."""
    data = dict(record_dict)
    data.pop("evaluated_at", None)
    data.pop("content_fingerprint", None)
    return data


def fingerprint_court_record(record_dict: dict[str, Any]) -> str:
    return fingerprint(court_record_stable_payload(record_dict))


def fingerprint_evidence(evidence: CourtEvidenceEnvelope) -> str:
    return fingerprint(evidence.to_dict())


def _blocked_record(
    *,
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope,
    evaluated_by: str,
    required: bool,
    failure_class: CourtFailureClass,
    summary: str,
    notes: str | None = None,
) -> CourtRecord:
    record_id = f"court-{uuid.uuid4().hex[:12]}"
    empty_checks = [
        CourtCheckOutcome(check_id=cid, result=CourtCheckResult.FAIL, findings=[])
        for cid in CourtCheckId
    ]
    # Mark as blocked — checks not meaningfully evaluated
    finding = _finding(
        CourtCheckId.CONSTITUTION_VIOLATION,
        failure_class.value,
        summary,
        severity=CourtFindingSeverity.BLOCKER,
    )
    empty_checks[0] = CourtCheckOutcome(
        check_id=CourtCheckId.CONSTITUTION_VIOLATION,
        result=CourtCheckResult.FAIL,
        findings=[finding],
    )
    rec = CourtRecord(
        schema_version=COURT_SCHEMA_VERSION,
        court_rules_version=COURT_RULES_VERSION,
        record_id=record_id,
        task_id=task.id,
        plan_id=plan.plan_id,
        project_id=plan.project_id,
        required=required,
        evaluated_by=evaluated_by,
        evaluated_at=utc_now_iso(),
        starting_commit=plan.starting_commit,
        verdict=CourtVerdict.BLOCKED,
        checks=empty_checks,
        findings=[finding],
        failure_classes=[failure_class.value],
        notes=notes or summary,
        task_fingerprint=fingerprint_task(task.to_dict()),
        plan_fingerprint=fingerprint_plan(plan.to_dict()),
        evidence_fingerprint=fingerprint_evidence(evidence),
        content_fingerprint="",
        next_action="fix registry/schema/rules/self-review and re-run",
    )
    rec.content_fingerprint = fingerprint_court_record(rec.to_dict())
    return rec


def evaluate_constitutional_court(
    task: Task,
    plan: Plan,
    evidence: CourtEvidenceEnvelope | None = None,
    *,
    evaluated_by: str,
    required: bool | None = None,
    force_required: bool | None = None,
    force_advisory: bool = False,
    safety_prefixes: Sequence[str] | None = None,
    required_prohibitions: Sequence[str] | None = None,
    court_rules_version: str = COURT_RULES_VERSION,
) -> CourtRecord:
    """Run five deterministic checks and aggregate a CourtRecord.

    Pure over structured inputs — no I/O, no network, no Equitify content reads.
    """
    ev = evidence or CourtEvidenceEnvelope()
    evaluated_by_norm = (evaluated_by or "").strip()
    if not evaluated_by_norm:
        # Usage error is raised by CLI; treat as blocked integrity failure here.
        return _blocked_record(
            task=task,
            plan=plan,
            evidence=ev,
            evaluated_by="",
            required=True,
            failure_class=CourtFailureClass.INTERNAL_ERROR,
            summary="evaluated_by is required",
        )

    # Schema / rules version gates
    if ev.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return _blocked_record(
            task=task,
            plan=plan,
            evidence=ev,
            evaluated_by=evaluated_by_norm,
            required=True,
            failure_class=CourtFailureClass.UNSUPPORTED_SCHEMA_VERSION,
            summary=f"unsupported evidence schema_version {ev.schema_version!r}",
        )
    if court_rules_version not in SUPPORTED_RULES_VERSIONS:
        return _blocked_record(
            task=task,
            plan=plan,
            evidence=ev,
            evaluated_by=evaluated_by_norm,
            required=True,
            failure_class=CourtFailureClass.UNSUPPORTED_RULES_VERSION,
            summary=f"unsupported court_rules_version {court_rules_version!r}",
        )

    major = is_major_change(task, plan, ev, safety_prefixes=safety_prefixes)
    if force_advisory:
        is_required = False
    elif force_required is True:
        is_required = True
    elif required is not None:
        is_required = required
    else:
        is_required = major

    # Independence: high/critical required runs cannot be self-reviewed by planner
    risk_high = task.risk_level in HIGH_RISK_LEVELS or plan.risk_level in HIGH_RISK_LEVELS
    if is_required and risk_high:
        planner = str(plan.planner_agent).strip()
        if planner.lower() == evaluated_by_norm.lower():
            return _blocked_record(
                task=task,
                plan=plan,
                evidence=ev,
                evaluated_by=evaluated_by_norm,
                required=is_required,
                failure_class=CourtFailureClass.SELF_REVIEW_FORBIDDEN,
                summary=(
                    "self_review_forbidden: evaluated_by must differ from planner_agent "
                    "for required high/critical Court runs"
                ),
            )

    checks = [
        check_constitution_violation(task, plan, ev, required=is_required),
        check_safety_regression(
            task,
            plan,
            ev,
            required=is_required,
            safety_prefixes=safety_prefixes,
            required_prohibitions=required_prohibitions,
        ),
        check_risk_increase(
            task, plan, ev, required=is_required, safety_prefixes=safety_prefixes
        ),
        check_reproducibility(task, plan, ev, required=is_required),
        check_measurability(task, plan, ev, required=is_required),
    ]
    assert len(checks) == 5

    flat: list[CourtFinding] = []
    for c in checks:
        flat.extend(c.findings)

    paths = collect_scope_paths(task, plan, ev)
    failing = [
        c
        for c in checks
        if c.result in (CourtCheckResult.FAIL, CourtCheckResult.INSUFFICIENT_EVIDENCE)
    ]
    notes_only = [
        f
        for f in flat
        if f.severity in (CourtFindingSeverity.MINOR, CourtFindingSeverity.NOTE)
    ]
    failure_classes = _failure_classes_for(checks, ev, paths)

    if failing:
        if not is_required:
            verdict = CourtVerdict.ADVISORY_ONLY
            next_action = "advisory findings recorded; approve-plan not blocked by Court"
        else:
            verdict = CourtVerdict.REJECTED
            next_action = "fix findings and re-run constitutional-check"
    elif notes_only:
        verdict = CourtVerdict.PASS_WITH_NOTES if is_required else CourtVerdict.PASS_WITH_NOTES
        if not is_required and major is False:
            # Still a clean advisory pass-with-notes
            pass
        next_action = (
            "approve-plan allowed"
            if is_required
            else "advisory pass_with_notes; approve-plan not gated"
        )
    else:
        verdict = CourtVerdict.PASS
        next_action = (
            "approve-plan allowed"
            if is_required
            else "advisory pass; approve-plan not gated"
        )

    # Special-case: low-risk advisory with no findings → pass (exit 0); design allows
    # advisory_only OR pass with notes for empty evidence advisory.
    if not is_required and not failing and not notes_only:
        verdict = CourtVerdict.PASS

    record_id = f"court-{uuid.uuid4().hex[:12]}"
    rec = CourtRecord(
        schema_version=COURT_SCHEMA_VERSION,
        court_rules_version=court_rules_version,
        record_id=record_id,
        task_id=task.id,
        plan_id=plan.plan_id,
        project_id=plan.project_id,
        required=is_required,
        evaluated_by=evaluated_by_norm,
        evaluated_at=utc_now_iso(),
        starting_commit=plan.starting_commit,
        verdict=verdict,
        checks=checks,
        findings=flat,
        failure_classes=failure_classes if failing else [],
        notes=None,
        task_fingerprint=fingerprint_task(task.to_dict()),
        plan_fingerprint=fingerprint_plan(plan.to_dict()),
        evidence_fingerprint=fingerprint_evidence(ev),
        content_fingerprint="",
        next_action=next_action,
    )
    rec.content_fingerprint = fingerprint_court_record(rec.to_dict())
    return rec


def court_record_satisfies_approval(record: CourtRecord, plan: Plan) -> bool:
    """True if record is a fresh matching pass usable for approve_plan."""
    if record.verdict not in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES):
        return False
    if not record.required:
        return False
    current_fp = fingerprint_plan(plan.to_dict())
    if record.plan_fingerprint != current_fp:
        return False
    if record.plan_id != plan.plan_id:
        return False
    return True


def exit_code_for_verdict(verdict: CourtVerdict) -> int:
    if verdict in (CourtVerdict.PASS, CourtVerdict.PASS_WITH_NOTES, CourtVerdict.ADVISORY_ONLY):
        return 0
    if verdict is CourtVerdict.REJECTED:
        return 2
    if verdict is CourtVerdict.BLOCKED:
        return 3
    return 3
