"""CLI helpers and evidence-bundle loading for Round 4C reporting commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .reporting_builder import EvidenceBundle, ReportingBuildError, build_canonical_report
from .reporting_constants import EQUITIFY_SENTINELS
from .reporting_models import (
    AcceptanceCriterionRow,
    CanonicalReportSnapshot,
    ClaimRecord,
    DetailLevel,
    EvidenceItem,
    NextAction,
    ReportAudience,
    RiskRecord,
    RootCauseRecord,
    SecurityFinding,
    UsageField,
)
from .reporting_renderer import render_markdown
from .reporting_store import CanonicalReportStore
from .reporting_validate import validate_snapshot


class ReportingCLIError(ValueError):
    pass


def _reject_paths(*parts: str | None) -> None:
    blob = " ".join(p or "" for p in parts).lower()
    for s in EQUITIFY_SENTINELS:
        if s in blob:
            raise ReportingCLIError(f"Prohibited path or identifier: {s}")
    for p in parts:
        if not p:
            continue
        if ".." in Path(p).parts:
            raise ReportingCLIError("Path escape rejected")


def evidence_bundle_from_dict(data: dict[str, Any]) -> EvidenceBundle:
    return EvidenceBundle(
        project_id=str(data["project_id"]),
        task_id=str(data["task_id"]),
        task_objective=str(data.get("task_objective") or ""),
        outcome=str(data.get("outcome") or ""),
        final_verdict=str(data.get("final_verdict") or ""),
        plan_id=data.get("plan_id"),
        orchestration_id=data.get("orchestration_id"),
        starting_commit=data.get("starting_commit"),
        final_commit=data.get("final_commit"),
        repository_identity=data.get("repository_identity"),
        evidence=[EvidenceItem.from_dict(e) for e in (data.get("evidence") or [])],
        claims=[ClaimRecord.from_dict(c) for c in (data.get("claims") or [])],
        acceptance=[
            AcceptanceCriterionRow.from_dict(r) for r in (data.get("acceptance") or [])
        ],
        approvals=list(data.get("approvals") or []),
        risks=[RiskRecord.from_dict(r) for r in (data.get("risks") or [])],
        blockers=list(data.get("blockers") or []),
        next_actions=[NextAction.from_dict(n) for n in (data.get("next_actions") or [])],
        root_causes=[RootCauseRecord.from_dict(r) for r in (data.get("root_causes") or [])],
        security_findings=[
            SecurityFinding.from_dict(s) for s in (data.get("security_findings") or [])
        ],
        usage_fields=[UsageField.from_dict(u) for u in (data.get("usage_fields") or [])],
        git_intelligence=dict(data.get("git_intelligence") or {}),
        test_intelligence=dict(data.get("test_intelligence") or {}),
        ci_intelligence=dict(data.get("ci_intelligence") or {}),
        dependency_intelligence=dict(data.get("dependency_intelligence") or {}),
        provider_orchestration=dict(data.get("provider_orchestration") or {}),
        repair_history=list(data.get("repair_history") or []),
        unresolved_conflicts=list(data.get("unresolved_conflicts") or []),
        unavailable_mandatory=list(data.get("unavailable_mandatory") or []),
        source_bindings=dict(data.get("source_bindings") or {}),
        documentation_only=bool(data.get("documentation_only")),
        workflow_blocked=bool(data.get("workflow_blocked")),
        legacy_marks=list(data.get("legacy_marks") or []),
        generated_at=data.get("generated_at"),
    )


def load_bundle(path: Path) -> EvidenceBundle:
    _reject_paths(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    return evidence_bundle_from_dict(data)


def build_and_persist(
    bundle: EvidenceBundle,
    *,
    audience: ReportAudience,
    detail_level: DetailLevel,
    workspace_root: Path | None = None,
    producer_version: str | None = None,
) -> CanonicalReportSnapshot:
    _reject_paths(bundle.project_id, bundle.task_id, bundle.repository_identity)
    snapshot = build_canonical_report(
        bundle,
        audience=audience,
        detail_level=detail_level,
        producer_version=producer_version,
    )
    store = CanonicalReportStore(workspace_root=workspace_root)
    store.save_canonical(snapshot)
    return snapshot


def render_and_persist(
    snapshot: CanonicalReportSnapshot,
    *,
    workspace_root: Path | None = None,
    allow_incomplete_diagnostic: bool = False,
    current_bindings: dict[str, Any] | None = None,
) -> tuple[str, Path]:
    result = validate_snapshot(
        snapshot,
        current_bindings=current_bindings,
        allow_incomplete_diagnostic=allow_incomplete_diagnostic,
    )
    if not result.ok and not allow_incomplete_diagnostic:
        raise ReportingCLIError(
            f"validate_failed:{result.failure_class.value}:{','.join(result.errors)}"
        )
    if result.report_status and result.report_status.value == "stale" and not allow_incomplete_diagnostic:
        raise ReportingCLIError("refuse_render_stale")
    if result.report_status and result.report_status.value == "invalid" and not allow_incomplete_diagnostic:
        raise ReportingCLIError("refuse_render_invalid")
    md = render_markdown(snapshot)
    store = CanonicalReportStore(workspace_root=workspace_root)
    path = store.save_rendered(snapshot, md)
    return md, path
