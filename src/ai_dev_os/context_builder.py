"""Minimal context packet builder — no full repo dump."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import Task, utc_now_iso
from .routing import get_budget_limits, select_token_budget_band

if TYPE_CHECKING:
    from .memory.service import MemoryService
    from .project_registry import ProjectRegistry


@dataclass
class ContextPacket:
    markdown: str
    manifest: dict[str, Any]
    markdown_path: Path | None = None
    manifest_path: Path | None = None


def build_context_packet(
    task: Task,
    project_root: str | Path,
    *,
    include_paths: list[str] | None = None,
    notes: str | None = None,
    include_approved_memory: bool = False,
    memory_service: MemoryService | None = None,
    registry: ProjectRegistry | None = None,
) -> ContextPacket:
    """Build a minimal markdown packet + JSON manifest for manual handoff.

    ``include_approved_memory`` defaults to False so existing callers
    (orchestration, providers) remain byte-identical. When True, the project
    must be opted in via ``ProjectRecord.memory_enabled`` and a
    ``MemoryService`` (or constructible via ``registry``) is required.
    """
    root = Path(project_root)
    band = task.token_budget_band or select_token_budget_band(task)
    budget = get_budget_limits(band)
    paths = include_paths if include_paths is not None else list(task.allowed_paths)
    # Cap path listing to keep packets minimal.
    capped_paths = paths[:40]
    truncated = len(paths) > len(capped_paths)

    lines = [
        f"# Context Packet — {task.id}",
        "",
        "## Task",
        f"- Title: {task.title}",
        f"- Project: {task.project_id}",
        f"- Type: {task.task_type.value}",
        f"- Complexity: {task.complexity.value}",
        f"- Risk: {task.risk_level.value}",
        f"- Status: {task.status.value}",
        f"- Assigned role: {task.assigned_role.value if task.assigned_role else 'unassigned'}",
        "",
        "## Description",
        task.description,
        "",
        "## Acceptance Criteria",
    ]
    if task.acceptance_criteria:
        lines.extend(f"- {c}" for c in task.acceptance_criteria)
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Scope Paths (minimal — not a full repo dump)",
            f"- Project root: `{root}`",
        ]
    )
    if capped_paths:
        lines.extend(f"- `{p}`" for p in capped_paths)
        if truncated:
            lines.append(f"- … truncated {len(paths) - len(capped_paths)} additional paths")
    else:
        lines.append("- (no explicit allowed paths; stay within project root)")

    if task.prohibited_paths:
        lines.append("")
        lines.append("## Prohibited Paths")
        lines.extend(f"- `{p}`" for p in task.prohibited_paths)

    lines.extend(
        [
            "",
            "## Token Budget",
            f"- Band: {budget['band']}",
            f"- Max input: {budget['max_input_tokens']}",
            f"- Max output: {budget['max_output_tokens']}",
            "",
            "## Routing",
            task.routing_explanation or "(not routed yet)",
            "",
            "## Constraints",
            "- Manual handoff only (`automation_status: manual_handoff_required`).",
            "- Do not call paid LLM APIs from the product.",
            "- Do not dump the full repository into context.",
            "- Do not read env secrets or store API keys.",
        ]
    )
    if notes:
        lines.extend(["", "## Notes", notes])

    memory_ids: list[str] = []
    if include_approved_memory:
        service = memory_service
        if service is None:
            if registry is None:
                from .memory.errors import MemoryDisabledError

                raise MemoryDisabledError(
                    "include_approved_memory requires a MemoryService or ProjectRegistry"
                )
            from .memory.service import MemoryService as _MemoryService

            service = _MemoryService(registry=registry)
        hits = service.retrieve(task.project_id)
        memory_ids = [h.memory_id for h in hits]
        if hits:
            lines.extend(["", "## Approved Project Memory"])
            for hit in hits:
                title = hit.title or hit.memory_id
                lines.append(f"- `{hit.memory_id}` ({hit.category.value}): {title}")
                # One-line content preview; full content stays in the store.
                preview = (hit.content or "").strip().replace("\n", " ")
                if len(preview) > 200:
                    preview = preview[:197] + "..."
                if preview:
                    lines.append(f"  - {preview}")

    markdown = "\n".join(lines) + "\n"
    manifest = {
        "task_id": task.id,
        "project_id": task.project_id,
        "project_root": str(root),
        "assigned_role": task.assigned_role.value if task.assigned_role else None,
        "token_budget": budget,
        "include_paths": capped_paths,
        "include_paths_truncated": truncated,
        "prohibited_paths": list(task.prohibited_paths),
        "created_at": utc_now_iso(),
        "full_repo_dump": False,
        "automation_status": "manual_handoff_required",
    }
    # Only add memory keys when explicitly requested — keeps default packets
    # byte-identical in shape to pre-B3.3 (aside from created_at).
    if include_approved_memory:
        manifest["approved_memory_ids"] = memory_ids
        manifest["include_approved_memory"] = True
    return ContextPacket(markdown=markdown, manifest=manifest)


def write_context_packet(
    packet: ContextPacket,
    output_dir: str | Path,
    task_id: str,
) -> ContextPacket:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{task_id}.context.md"
    json_path = out / f"{task_id}.context.json"
    md_path.write_text(packet.markdown, encoding="utf-8")
    json_path.write_text(json.dumps(packet.manifest, indent=2) + "\n", encoding="utf-8")
    packet.markdown_path = md_path
    packet.manifest_path = json_path
    return packet
