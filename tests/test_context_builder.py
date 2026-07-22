"""Context builder tests — minimal packet, no full dump."""

from pathlib import Path

from ai_dev_os.context_builder import build_context_packet, write_context_packet
from ai_dev_os.models import Complexity, RiskLevel, Task, TaskType
from ai_dev_os.routing import apply_routing


def test_context_packet_minimal(tmp_path: Path):
    task = apply_routing(
        Task(
            id="ctx1",
            title="Build packet",
            description="Only essentials",
            project_id="demo",
            task_type=TaskType.FEATURE,
            complexity=Complexity.SMALL,
            risk_level=RiskLevel.LOW,
            allowed_paths=[f"f{i}.py" for i in range(50)],
        )
    )
    packet = build_context_packet(task, tmp_path)
    assert "full repository" in packet.markdown.lower() or "not a full repo dump" in packet.markdown.lower()
    assert packet.manifest["full_repo_dump"] is False
    assert packet.manifest["automation_status"] == "manual_handoff_required"
    assert packet.manifest["include_paths_truncated"] is True
    assert len(packet.manifest["include_paths"]) == 40

    written = write_context_packet(packet, tmp_path / "out", task.id)
    assert written.markdown_path.exists()
    assert written.manifest_path.exists()
