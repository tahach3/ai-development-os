"""Operator decision records for distinct trusted provider CLIs (Round 4D1.1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from .fingerprints import fingerprint
from .models import utc_now_iso
from .provider_readiness_ambiguity import AmbiguityResolutionResult, EnrichedCandidate
from .provider_readiness_constants import OPERATOR_SELECTION_SCHEMA_VERSION
from .provider_readiness_pins import host_binding_fingerprint
from .safe_policy import PolicyError, assert_not_equitify_blob

APPROVAL_PHRASE_TEMPLATE = (
    "Approve provider executable {candidate_id} for local readiness pinning only."
)


def default_decisions_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "workspace" / "provider_selection_decisions"


@dataclass
class OperatorDecisionRecord:
    decision_id: str
    schema_version: str
    provider_id: str
    host_binding_fingerprint: str
    candidate_ids: list[str]
    candidates: list[dict[str, Any]]
    recommended_candidate_id: str | None
    recommendation_reasons: list[str]
    recommendation_evidence_ids: list[str]
    risks_by_candidate: dict[str, list[str]]
    approval_phrase: str
    decision_status: str
    staleness_inputs: dict[str, str]
    created_at: str
    decision_fingerprint: str = ""
    notes: str = ""

    def compute_fingerprint(self) -> str:
        payload = asdict(self)
        payload.pop("decision_fingerprint", None)
        payload.pop("created_at", None)
        return fingerprint(payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperatorDecisionRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)


def approval_phrase_for(candidate_id: str) -> str:
    return APPROVAL_PHRASE_TEMPLATE.format(candidate_id=candidate_id)


def validate_approval_phrase(phrase: str, candidate_id: str) -> bool:
    return phrase.strip() == approval_phrase_for(candidate_id)


def recommend_candidate(
    candidates: list[EnrichedCandidate],
) -> tuple[str | None, list[str], list[str]]:
    """Deterministic recommendation — never PATH-only selection."""
    trusted = [c for c in candidates if c.trust_status == "trusted"]
    if not trusted:
        return None, ["no_trusted_candidate"], []

    def score(c: EnrichedCandidate) -> tuple:
        # Lower is better.
        compat = 0 if (c.compatibility_status or "supported") == "supported" else 1
        if c.compatibility_status == "unsupported":
            compat = 5
        provenance_score = 0
        if "configured" in c.discovery_methods:
            provenance_score = 0
        elif c.wrapper_type in {"none", "symlink_alias"}:
            provenance_score = 1
        elif c.wrapper_supported:
            provenance_score = 2
        else:
            provenance_score = 4
        wrapper_complexity = 0 if c.wrapper_type == "none" else 1
        path_rank = c.path_rank if c.path_rank is not None else 9_999
        return (
            compat,
            provenance_score,
            wrapper_complexity,
            0 if c.fingerprint else 1,
            path_rank,  # lowest priority informational
            c.candidate_id,
        )

    ranked = sorted(trusted, key=score)
    best = ranked[0]
    reasons = [
        "rec_rule_supported_version_pref",
        "rec_rule_trusted_provenance",
        "rec_rule_stable_non_wrapper_pref",
        "rec_rule_path_rank_informational_only",
    ]
    evidence = list(best.evidence_ids)
    return best.candidate_id, reasons, evidence


def build_operator_decision(
    resolution: AmbiguityResolutionResult,
) -> OperatorDecisionRecord:
    if not resolution.requires_operator_selection:
        raise PolicyError("Operator decision only valid when selection is required")

    # Candidates that belong to distinct logical installations
    selectable = [
        c
        for c in resolution.candidates
        if c.candidate_id not in resolution.rejected_candidate_ids
        and c.trust_status == "trusted"
    ]
    # One representative per logical installation
    reps: list[EnrichedCandidate] = []
    seen_logic = set()
    for li in resolution.logical_installations:
        if li.logical_installation_id in seen_logic:
            continue
        seen_logic.add(li.logical_installation_id)
        inv = next(
            (c for c in selectable if c.candidate_id == li.selected_invocation_candidate_id),
            None,
        )
        if inv:
            reps.append(inv)
        else:
            for cid in li.candidate_ids:
                hit = next((c for c in selectable if c.candidate_id == cid), None)
                if hit:
                    reps.append(hit)
                    break

    recommended_id, reasons, evid = recommend_candidate(reps or selectable)
    risks: dict[str, list[str]] = {}
    for c in reps or selectable:
        rlist = []
        if c.wrapper_type != "none":
            rlist.append("wrapper_indirection")
        if not c.fingerprint:
            rlist.append("missing_fingerprint")
        if c.compatibility_status == "unsupported":
            rlist.append("unsupported_version")
        if c.path_rank == 0:
            rlist.append("path_precedence_not_trust")
        risks[c.candidate_id] = rlist or ["standard_local_cli_risk"]

    phrase = (
        approval_phrase_for(recommended_id)
        if recommended_id
        else "No candidate available for approval."
    )
    public_candidates = [c.to_public_dict() for c in (reps or selectable)]
    record = OperatorDecisionRecord(
        decision_id=f"odec_{uuid4().hex[:16]}",
        schema_version=OPERATOR_SELECTION_SCHEMA_VERSION,
        provider_id=resolution.provider_id,
        host_binding_fingerprint=host_binding_fingerprint(),
        candidate_ids=[c.candidate_id for c in (reps or selectable)],
        candidates=public_candidates,
        recommended_candidate_id=recommended_id,
        recommendation_reasons=reasons,
        recommendation_evidence_ids=evid,
        risks_by_candidate=risks,
        approval_phrase=phrase,
        decision_status="operator_selection_required",
        staleness_inputs={
            "ambiguity_schema": resolution.schema_version,
            "identity_policy": resolution.identity_policy_version,
            "host_binding": host_binding_fingerprint(),
        },
        created_at=utc_now_iso(),
        notes="Live mode remains disabled until separate Round 4D2 authorization.",
    )
    record.decision_fingerprint = record.compute_fingerprint()
    return record


class OperatorDecisionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_decisions_root()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".gitkeep").touch(exist_ok=True)

    def save(self, record: OperatorDecisionRecord) -> Path:
        assert_not_equitify_blob(record.decision_id)
        if not record.decision_fingerprint:
            record.decision_fingerprint = record.compute_fingerprint()
        path = self.root / f"{record.decision_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def load(self, decision_id: str) -> OperatorDecisionRecord:
        assert_not_equitify_blob(decision_id)
        path = self.root / f"{decision_id}.json"
        if not path.is_file():
            raise PolicyError(f"Decision record not found: {decision_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return OperatorDecisionRecord.from_dict(data)
