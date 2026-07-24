"""Phase B3.3 — memory service opt-in, lifecycle, audit, context_builder consumer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_dev_os.context_builder import build_context_packet
from ai_dev_os.memory import (
    DEFAULT_MEMORY_CONFIG,
    EvidenceStrength,
    LifecycleStatus,
    MemoryActorRole,
    MemoryAuthorizationError,
    MemoryCategory,
    MemoryClass,
    MemoryConfig,
    MemoryDisabledError,
    MemoryService,
    MemorySourceType,
    set_project_memory_enabled,
)
from ai_dev_os.models import (
    Complexity,
    ModelRole,
    ProjectRecord,
    RiskLevel,
    Task,
    TaskType,
)
from ai_dev_os.project_registry import ProjectRegistry


def _registry(tmp_path: Path, *, memory_enabled: bool = False) -> ProjectRegistry:
    path = tmp_path / "projects.yaml"
    path.write_text("projects: []\n", encoding="utf-8")
    registry = ProjectRegistry(path)
    registry.register(
        ProjectRecord(
            id="demo",
            name="Demo",
            root_path=str(tmp_path / "proj"),
            memory_enabled=memory_enabled,
        )
    )
    (tmp_path / "proj").mkdir(exist_ok=True)
    return registry


def _service(tmp_path: Path, registry: ProjectRegistry) -> MemoryService:
    db = tmp_path / "memory.sqlite3"
    return MemoryService(
        registry=registry,
        db_path=db,
        root=tmp_path,
        config=MemoryConfig(
            enabled=False,  # global default remains false; service enables sessionally
            db_path=str(db),
            audit_retrievals=True,
        ),
    )


def _task(project_id: str = "demo") -> Task:
    return Task(
        id="task-mem-1",
        title="Memory consumer task",
        description="Build a packet",
        project_id=project_id,
        task_type=TaskType.FEATURE,
        complexity=Complexity.NORMAL,
        risk_level=RiskLevel.LOW,
        acceptance_criteria=["ok"],
        allowed_paths=["src/"],
        assigned_role=ModelRole.CURSOR,
        routing_explanation="test",
        token_budget_band=Complexity.NORMAL,
    )


def test_global_default_still_disabled():
    assert DEFAULT_MEMORY_CONFIG.enabled is False


def test_opt_out_project_refuses_like_b32(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=False)
    service = _service(tmp_path, registry)
    with pytest.raises(MemoryDisabledError):
        service.propose(
            {
                "project_id": "demo",
                "content": "a fact",
                "category": MemoryCategory.PROJECT_FACT.value,
                "proposed_by": "operator:alice",
                "source_type": MemorySourceType.OPERATOR.value,
            },
            actor="operator:alice",
        )
    assert not (tmp_path / "memory.sqlite3").exists()


def test_opt_in_lifecycle_and_permissions(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=True)
    service = _service(tmp_path, registry)

    proposed = service.propose(
        {
            "project_id": "demo",
            "content": "Calculator uses NFKC",
            "category": MemoryCategory.PROJECT_FACT.value,
            "proposed_by": "cursor-agent",
            "source_type": MemorySourceType.CURSOR.value,
            "title": "NFKC",
        },
        actor="cursor-agent",
        actor_role=MemoryActorRole.CURSOR,
    )
    assert proposed.lifecycle_status is LifecycleStatus.PROPOSED

    with pytest.raises(MemoryAuthorizationError):
        service.approve(
            "demo",
            proposed.memory_id,
            approver="cursor-agent",
            actor_role=MemoryActorRole.CURSOR,
        )

    validated = service.validate(
        "demo",
        proposed.memory_id,
        actor="os",
        actor_role=MemoryActorRole.OS_CONTROL_PLANE,
    )
    assert validated.lifecycle_status is LifecycleStatus.VALIDATED

    approved = service.approve(
        "demo",
        proposed.memory_id,
        approver="operator:alice",
        actor_role=MemoryActorRole.HUMAN_OPERATOR,
    )
    assert approved.lifecycle_status is LifecycleStatus.APPROVED
    assert approved.memory_class is MemoryClass.APPROVED

    hits = service.retrieve("demo", audit=False)
    assert len(hits) == 1
    assert hits[0].memory_id == approved.memory_id


def test_forget_and_hard_delete_audit(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=True)
    service = _service(tmp_path, registry)
    rec = service.propose(
        {
            "project_id": "demo",
            "content": "temporary fact",
            "category": MemoryCategory.LESSON.value,
            "proposed_by": "operator:bob",
            "source_type": MemorySourceType.OPERATOR.value,
        },
        actor="operator:bob",
    )
    service.validate("demo", rec.memory_id, actor="os")
    service.approve("demo", rec.memory_id, approver="operator:bob")

    forgotten = service.forget("demo", rec.memory_id, actor="operator:bob")
    assert forgotten.lifecycle_status is LifecycleStatus.FORGOTTEN
    assert forgotten.forgotten_at
    assert forgotten.content == "temporary fact"
    assert service.retrieve("demo", audit=False) == ()

    erased = service.hard_delete("demo", rec.memory_id, actor="operator:bob")
    assert erased.content_erased_at
    assert not (erased.content or "").strip()

    events = service.list_events("demo", memory_id=rec.memory_id, limit=50)
    actions = [e["action"] for e in events]
    assert "forget" in actions
    assert "hard_delete" in actions
    assert "propose" in actions
    assert "approve" in actions


def test_model_cannot_hard_delete(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=True)
    service = _service(tmp_path, registry)
    rec = service.propose(
        {
            "project_id": "demo",
            "content": "x",
            "category": MemoryCategory.OTHER.value,
            "proposed_by": "op",
            "source_type": MemorySourceType.OPERATOR.value,
        },
        actor="op",
    )
    with pytest.raises(MemoryAuthorizationError):
        service.hard_delete(
            "demo",
            rec.memory_id,
            actor="cursor",
            actor_role=MemoryActorRole.CURSOR,
        )


def test_deterministic_retrieve_ordering(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=True)
    service = _service(tmp_path, registry)

    def _approve(content: str, strength: EvidenceStrength, approved_at: str, mid: str):
        # Use service propose then patch via repo update for fixed timestamps/strength.
        proposed = service.propose(
            {
                "project_id": "demo",
                "content": content,
                "category": MemoryCategory.PROJECT_FACT.value,
                "proposed_by": "op",
                "source_type": MemorySourceType.OPERATOR.value,
                "memory_id": mid,
            },
            actor="op",
        )
        service.validate("demo", proposed.memory_id, actor="os")
        approved = service.approve(
            "demo", proposed.memory_id, approver="op"
        )
        # Re-open repo to adjust strength + approved_at deterministically.
        from dataclasses import replace

        from ai_dev_os.memory import SqliteMemoryRepository

        db = tmp_path / "memory.sqlite3"
        cfg = MemoryConfig(enabled=True, db_path=str(db), audit_retrievals=False)
        repo = SqliteMemoryRepository(str(db), config=cfg, root=str(tmp_path))
        current = repo.get_record("demo", approved.memory_id)
        patched = replace(
            current,
            evidence_strength=strength,
            approved_at=approved_at,
            updated_at=approved_at,
        )
        repo.update_record(patched)
        return approved.memory_id

    # Fixed memory ids so tie-break is deterministic.
    id_weak_old = "mem-aaaaaaaaaaaa"
    id_strong = "mem-bbbbbbbbbbbb"
    id_weak_new = "mem-cccccccccccc"
    _approve("weak old", EvidenceStrength.WEAK, "2026-01-01T00:00:00+00:00", id_weak_old)
    _approve("strong", EvidenceStrength.STRONG, "2026-01-01T00:00:00+00:00", id_strong)
    _approve("weak new", EvidenceStrength.WEAK, "2026-06-01T00:00:00+00:00", id_weak_new)

    hits = service.retrieve("demo", audit=False)
    assert [h.memory_id for h in hits] == [id_strong, id_weak_new, id_weak_old]


def test_context_builder_default_byte_identical_shape(tmp_path: Path):
    """Non-opted / default path must not add memory sections or manifest keys."""
    task = _task()
    packet = build_context_packet(task, tmp_path / "proj")
    assert "## Approved Project Memory" not in packet.markdown
    assert "approved_memory_ids" not in packet.manifest
    assert "include_approved_memory" not in packet.manifest
    # Canonical pre-B3.3 manifest keys (created_at excluded as wall-clock).
    expected_keys = {
        "task_id",
        "project_id",
        "project_root",
        "assigned_role",
        "token_budget",
        "include_paths",
        "include_paths_truncated",
        "prohibited_paths",
        "created_at",
        "full_repo_dump",
        "automation_status",
    }
    assert set(packet.manifest.keys()) == expected_keys


def test_context_builder_include_memory_requires_opt_in(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=False)
    service = _service(tmp_path, registry)
    task = _task()
    with pytest.raises(MemoryDisabledError):
        build_context_packet(
            task,
            tmp_path / "proj",
            include_approved_memory=True,
            memory_service=service,
            registry=registry,
        )


def test_context_builder_includes_approved_when_opted_in(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=True)
    service = _service(tmp_path, registry)
    proposed = service.propose(
        {
            "project_id": "demo",
            "content": "Use stdlib sqlite3 only",
            "category": MemoryCategory.ARCHITECTURE_DECISION.value,
            "proposed_by": "op",
            "source_type": MemorySourceType.OPERATOR.value,
            "title": "SQLite only",
        },
        actor="op",
    )
    service.validate("demo", proposed.memory_id, actor="os")
    service.approve("demo", proposed.memory_id, approver="op")

    packet = build_context_packet(
        _task(),
        tmp_path / "proj",
        include_approved_memory=True,
        memory_service=service,
        registry=registry,
    )
    assert "## Approved Project Memory" in packet.markdown
    assert proposed.memory_id in packet.markdown
    assert packet.manifest["include_approved_memory"] is True
    assert packet.manifest["approved_memory_ids"] == [proposed.memory_id]


def test_set_project_memory_enabled_persists(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=False)
    set_project_memory_enabled(registry, "demo", True)
    reloaded = ProjectRegistry(registry.path)
    assert reloaded.require("demo").memory_enabled is True
    raw = yaml.safe_load(registry.path.read_text(encoding="utf-8"))
    assert raw["projects"][0]["memory_enabled"] is True


def test_reject_path(tmp_path: Path):
    registry = _registry(tmp_path, memory_enabled=True)
    service = _service(tmp_path, registry)
    rec = service.propose(
        {
            "project_id": "demo",
            "content": "bad idea",
            "category": MemoryCategory.OTHER.value,
            "proposed_by": "op",
            "source_type": MemorySourceType.OPERATOR.value,
        },
        actor="op",
    )
    rejected = service.reject(
        "demo", rec.memory_id, reason="not useful", actor="op"
    )
    assert rejected.lifecycle_status is LifecycleStatus.REJECTED
    assert service.retrieve("demo", audit=False) == ()
