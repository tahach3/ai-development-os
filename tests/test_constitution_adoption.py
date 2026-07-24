"""Project Sentinel — Constitution / Self-Build Strategy adoption checks."""

from __future__ import annotations

from pathlib import Path

from ai_dev_os import __version__
from ai_dev_os.ci_config import load_ci_policy
from ai_dev_os.ci_stages import STAGE_FUNCS, stage_doc_consistency

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_constitution_doc_exists_nonempty():
    path = REPO_ROOT / "docs" / "CONSTITUTION.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8").strip()
    assert text
    assert "AI Development OS Constitution v1.0" in text


def test_self_build_strategy_doc_exists_nonempty():
    path = REPO_ROOT / "docs" / "SELF_BUILD_STRATEGY.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8").strip()
    assert text
    assert "long-term vision, not implementation status" in text
    assert "Self-Build Strategy (Claude Master Handoff)" in text


def test_readme_or_roadmap_reference_governance_paths():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (REPO_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    combined = readme + "\n" + roadmap
    assert "docs/CONSTITUTION.md" in combined or "CONSTITUTION.md" in combined
    assert "docs/SELF_BUILD_STRATEGY.md" in combined or "SELF_BUILD_STRATEGY.md" in combined
    # Prefer explicit path forms used in docs links
    assert "CONSTITUTION.md" in readme or "CONSTITUTION.md" in roadmap
    assert "SELF_BUILD_STRATEGY.md" in readme or "SELF_BUILD_STRATEGY.md" in roadmap


def test_doc_consistency_stage_still_passes():
    policy = load_ci_policy(REPO_ROOT / "config" / "ci_policy.yaml")
    result = stage_doc_consistency(REPO_ROOT, policy)
    assert result.validation_status == "passed"
    assert "doc_consistency" in STAGE_FUNCS


def test_package_version_project_sentinel():
    assert __version__ == "0.8.12"
