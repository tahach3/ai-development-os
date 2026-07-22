"""Base adapter interfaces — manual handoff only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..context_builder import ContextPacket, build_context_packet, write_context_packet
from ..models import ModelRole, Task, utc_now_iso


AUTOMATION_STATUS = "manual_handoff_required"


@dataclass
class AdapterResult:
    role: ModelRole
    handoff_path: Path
    automation_status: str
    message: str


class BaseAdapter(ABC):
    role: ModelRole

    @abstractmethod
    def prepare_handoff(
        self,
        task: Task,
        project_root: str | Path,
        output_dir: str | Path,
    ) -> AdapterResult:
        raise NotImplementedError


class ManualHandoffAdapter(BaseAdapter):
    """Placeholder adapter that writes a handoff file; never calls network/APIs."""

    role: ModelRole
    display_name: str

    def prepare_handoff(
        self,
        task: Task,
        project_root: str | Path,
        output_dir: str | Path,
    ) -> AdapterResult:
        packet = build_context_packet(task, project_root)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_context_packet(packet, out, task.id)

        handoff_path = out / f"{task.id}.{self.role.value}.handoff.md"
        body = self._render_handoff(task, packet)
        handoff_path.write_text(body, encoding="utf-8")
        return AdapterResult(
            role=self.role,
            handoff_path=handoff_path,
            automation_status=AUTOMATION_STATUS,
            message=(
                f"{self.display_name} handoff ready at {handoff_path}. "
                "Manual paste into the tool is required; no API call was made."
            ),
        )

    def _render_handoff(self, task: Task, packet: ContextPacket) -> str:
        return "\n".join(
            [
                f"# {self.display_name} Manual Handoff",
                "",
                f"- Task ID: {task.id}",
                f"- Role: {self.role.value}",
                f"- Generated: {utc_now_iso()}",
                f"- automation_status: {AUTOMATION_STATUS}",
                "",
                "## Instructions",
                f"1. Open {self.display_name} manually.",
                "2. Paste the context packet below.",
                "3. Perform the work outside this OS process.",
                "4. Record results with `ai-dev-os record-report`.",
                "",
                "## Context Packet",
                "",
                packet.markdown,
                "",
                "## Safety",
                "- No paid LLM API calls from ai-dev-os.",
                "- No network requests from this adapter.",
                "- Do not execute generated code automatically.",
                "",
            ]
        )
