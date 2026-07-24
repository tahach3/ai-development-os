"""Phase B3.1 shared-memory domain foundations — unit tests."""

from __future__ import annotations

import pytest

from ai_dev_os.ci_secrets import redact_secrets, scan_text
from ai_dev_os.fingerprints import canonical_json, sha256_hex
from ai_dev_os.memory import (
    DEFAULT_MEMORY_CONFIG,
    MEMORY_FINGERPRINT_VERSION,
    MEMORY_NORMALIZATION_VERSION,
    MEMORY_POLICY_VERSION,
    MEMORY_SCHEMA_VERSION,
    ApprovalMethod,
    EvidenceStrength,
    LifecycleStatus,
    MemoryAction,
    MemoryActorRole,
    MemoryAuthorizationError,
    MemoryCategory,
    MemoryClass,
    MemoryConfig,
    MemoryConflictError,
    MemoryDisabledError,
    MemoryEvidenceRef,
    MemoryEvidenceType,
    MemoryRecord,
    MemorySecurityError,
    MemorySourceType,
    MemoryValidationError,
    Sensitivity,
    authorize_memory_action,
    compute_content_hash,
    memory_canonical_json,
    memory_sha256_hex,
    new_memory_evidence_id,
    new_memory_id,
    normalize_memory_content,
    prepare_candidate_record,
    refuse_secrets_in_text,
    validate_class_status_pairing,
    validate_content_hash,
    validate_lifecycle_transition,
    validate_propose_dict,
    validate_sensitivity_for_persist,
)
from ai_dev_os.memory.hashing import build_memory_fingerprint_payload


def _candidate_kwargs(**overrides):
    base = {
        "memory_id": new_memory_id(),
        "project_id": "demo-project",
        "category": MemoryCategory.PROJECT_FACT,
        "content": "  Calculator  uses   NFKC   rules  ",
        "proposed_by": "operator:alice",
        "source_type": MemorySourceType.OPERATOR,
        "title": "Calc fact",
        "sensitivity": Sensitivity.INTERNAL,
        "evidence_strength": EvidenceStrength.NONE,
        "memory_class": MemoryClass.CANDIDATE,
        "lifecycle_status": LifecycleStatus.PROPOSED,
    }
    base.update(overrides)
    return base


def test_default_config_disabled_and_require_enabled():
    assert DEFAULT_MEMORY_CONFIG.enabled is False
    assert isinstance(DEFAULT_MEMORY_CONFIG, MemoryConfig)
    with pytest.raises(MemoryDisabledError):
        DEFAULT_MEMORY_CONFIG.require_enabled()
    enabled = MemoryConfig(enabled=True)
    enabled.require_enabled()  # does not raise


def test_version_constants_independent_of_package():
    assert MEMORY_SCHEMA_VERSION == "memory.1"
    assert MEMORY_POLICY_VERSION == "memory.1"
    assert MEMORY_NORMALIZATION_VERSION == "memory.1"
    assert MEMORY_FINGERPRINT_VERSION == "memory.1"
    import ai_dev_os

    assert ai_dev_os.__version__ == "0.8.12"


def test_id_prefixes_and_immutability():
    mid = new_memory_id()
    eid = new_memory_evidence_id()
    assert mid.startswith("mem-") and len(mid) == 16
    assert eid.startswith("evid-") and len(eid) == 17
    record = MemoryRecord(**_candidate_kwargs())
    with pytest.raises(Exception):
        record.content = "mutated"  # type: ignore[misc]


def test_normalization_nfkc_casefold_collapse():
    # Fullwidth digits + mixed case + whitespace
    raw = "ＡＢＣ   Fact"
    normalized = normalize_memory_content(raw)
    assert normalized == "abc fact"
    assert "  " not in normalized


def test_secret_refuse_reuses_ci_secrets_without_leaking():
    # Build synthetic secret material at runtime so tracked source avoids secret_scan hits.
    secret_line = "api_key = " + '"' + "sk_live_" + ("a" * 26) + "0123" + '"'
    findings = scan_text("probe.py", secret_line)
    assert findings  # existing utility still detects
    with pytest.raises(MemorySecurityError) as exc:
        refuse_secrets_in_text(secret_line)
    msg = str(exc.value)
    assert "sk_live" not in msg
    assert "api_key_assignment" in msg
    assert "[REDACTED]" in redact_secrets(secret_line)


def test_secret_prohibited_sensitivity_fails_before_persist():
    with pytest.raises(MemorySecurityError):
        validate_sensitivity_for_persist(Sensitivity.SECRET_PROHIBITED)
    with pytest.raises(MemorySecurityError):
        prepare_candidate_record(
            MemoryRecord(**_candidate_kwargs(sensitivity=Sensitivity.SECRET_PROHIBITED))
        )


def test_prepare_candidate_sets_normalized_and_hash_stable():
    a = prepare_candidate_record(MemoryRecord(**_candidate_kwargs()))
    b = prepare_candidate_record(
        MemoryRecord(**_candidate_kwargs(memory_id=new_memory_id()))
    )
    assert a.content_normalized == "calculator uses nfkc rules"
    assert a.content_hash and len(a.content_hash) == 64
    # Same semantic content → same hash (ids excluded from fingerprint)
    assert a.content_hash == b.content_hash
    validate_content_hash(a)


def test_hash_wrapper_delegates_to_shared_canonical_json():
    payload = {"b": 2, "a": 1}
    assert memory_canonical_json(payload) == canonical_json(payload)
    assert memory_sha256_hex(payload) == sha256_hex(payload)
    # Shared helper behavior unchanged
    assert canonical_json({"z": 1, "a": 2}) == '{"a":2,"z":1}'


def test_stale_hash_fails_closed():
    record = prepare_candidate_record(MemoryRecord(**_candidate_kwargs()))
    with pytest.raises(MemoryConflictError):
        validate_content_hash(record, expected="0" * 64)


def test_lifecycle_transitions_and_pairings():
    validate_lifecycle_transition(LifecycleStatus.PROPOSED, LifecycleStatus.VALIDATED)
    validate_lifecycle_transition(LifecycleStatus.VALIDATED, LifecycleStatus.APPROVED)
    with pytest.raises(MemoryConflictError):
        validate_lifecycle_transition(LifecycleStatus.PROPOSED, LifecycleStatus.APPROVED)
    validate_class_status_pairing(MemoryClass.CANDIDATE, LifecycleStatus.PROPOSED)
    with pytest.raises(MemoryValidationError):
        validate_class_status_pairing(MemoryClass.APPROVED, LifecycleStatus.PROPOSED)


def test_models_cannot_approve_or_hard_delete():
    for role in (
        MemoryActorRole.CLAUDE,
        MemoryActorRole.CURSOR,
        MemoryActorRole.CODEX,
        MemoryActorRole.PROVIDER,
        MemoryActorRole.ORCHESTRATION,
    ):
        authorize_memory_action(role, MemoryAction.PROPOSE)
        with pytest.raises(MemoryAuthorizationError):
            authorize_memory_action(role, MemoryAction.APPROVE)
        with pytest.raises(MemoryAuthorizationError):
            authorize_memory_action(role, MemoryAction.HARD_DELETE)

    authorize_memory_action(MemoryActorRole.HUMAN_OPERATOR, MemoryAction.APPROVE)
    authorize_memory_action(MemoryActorRole.HUMAN_OPERATOR, MemoryAction.HARD_DELETE)
    authorize_memory_action(MemoryActorRole.OS_CONTROL_PLANE, MemoryAction.VALIDATE)
    with pytest.raises(MemoryAuthorizationError):
        authorize_memory_action(MemoryActorRole.OS_CONTROL_PLANE, MemoryAction.HARD_DELETE)


def test_validate_propose_dict_and_rejection_reason():
    record = validate_propose_dict(
        {
            "project_id": "demo",
            "category": "lesson",
            "content": "Prefer isolated worktrees for pytest",
            "proposed_by": "cursor",
            "source_type": "cursor",
            "evidence": [
                {
                    "evidence_id": new_memory_evidence_id(),
                    "evidence_type": MemoryEvidenceType.OPERATOR_NOTE.value,
                    "evidence_ref": "note-1",
                }
            ],
        }
    )
    assert record.memory_class is MemoryClass.CANDIDATE
    assert record.content_hash

    approved_data = record.to_dict()
    approved_data["memory_class"] = MemoryClass.APPROVED.value
    approved_data["lifecycle_status"] = LifecycleStatus.APPROVED.value
    approved_data["approved_by"] = "operator:alice"
    approved_data["approval_method"] = ApprovalMethod.HUMAN.value
    MemoryRecord.from_dict(approved_data)  # shape ok

    bad = record.to_dict()
    bad["memory_class"] = MemoryClass.REJECTED.value
    bad["lifecycle_status"] = LifecycleStatus.REJECTED.value
    bad["rejection_reason"] = None
    with pytest.raises(MemoryValidationError):
        from ai_dev_os.memory.validation import validate_memory_record_fields

        validate_memory_record_fields(MemoryRecord.from_dict(bad))


def test_fingerprint_payload_includes_versions_and_sorted_evidence():
    e1 = MemoryEvidenceRef(
        evidence_id=new_memory_evidence_id(),
        evidence_type=MemoryEvidenceType.CI_RUN,
        evidence_ref="ci_bbb",
    )
    e2 = MemoryEvidenceRef(
        evidence_id=new_memory_evidence_id(),
        evidence_type=MemoryEvidenceType.CI_RUN,
        evidence_ref="ci_aaa",
    )
    payload = build_memory_fingerprint_payload(
        project_id="p",
        category=MemoryCategory.LESSON.value,
        content_normalized="hello",
        sensitivity=Sensitivity.INTERNAL.value,
        memory_class=MemoryClass.CANDIDATE.value,
        lifecycle_status=LifecycleStatus.PROPOSED.value,
        evidence_strength=EvidenceStrength.MODERATE.value,
        source_type=MemorySourceType.SYSTEM.value,
        proposed_by="os",
        evidence=(e1, e2),
    )
    refs = payload["evidence_refs"]
    assert refs[0]["evidence_ref"] == "ci_aaa"
    assert payload["memory_fingerprint_version"] == MEMORY_FINGERPRINT_VERSION
    assert compute_content_hash(payload) == memory_sha256_hex(payload)


def test_no_ephemeral_context_class():
    values = {c.value for c in MemoryClass}
    assert "ephemeral_context" not in values


def test_compatibility_shared_fingerprint_and_secret_scan_unchanged():
    """Prove Round 4 helpers still behave the same when memory wrappers exist."""
    payload = {"task_id": "t1", "outcome": "success"}
    assert sha256_hex(payload) == memory_sha256_hex(payload)
    safe = scan_text("f.py", 'api_key = "YOUR_API_KEY"')
    assert safe == []
