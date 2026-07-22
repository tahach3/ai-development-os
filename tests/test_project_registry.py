"""Project registry separation and prohibited path tests (synthetic dirs only)."""

from pathlib import Path

import pytest

from ai_dev_os.models import ProjectRecord
from ai_dev_os.project_registry import ProjectRegistry, ProjectRegistryError
from ai_dev_os.task_store import TaskStore
from ai_dev_os.cli import main


def test_unregistered_repo_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    with pytest.raises(ProjectRegistryError, match="Unregistered"):
        registry.require("missing")


def test_task_for_missing_project_rejected(tmp_path: Path, monkeypatch):
    # CLI create-task should refuse missing project.
    # Use a temp registry with no projects.
    registry_path = tmp_path / "projects.yaml"
    registry_path.write_text("projects: []\n", encoding="utf-8")
    monkeypatch.setattr(
        "ai_dev_os.cli.ProjectRegistry",
        lambda: ProjectRegistry(registry_path),
    )
    code = main(
        [
            "create-task",
            "--project-id",
            "nope",
            "--id",
            "t1",
            "--title",
            "x",
            "--description",
            "y",
        ]
    )
    assert code == 1


def test_prohibited_paths_rejected(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    root = tmp_path / "proj"
    root.mkdir()
    secret = root / "secrets"
    secret.mkdir()
    registry.register(
        ProjectRecord(
            id="demo",
            name="Demo",
            root_path=str(root),
            prohibited_path_prefixes=[str(secret)],
        )
    )
    with pytest.raises(ProjectRegistryError, match="prohibited"):
        registry.ensure_path_allowed("demo", str(secret / "key.txt"))


def test_equitify_registration_refused(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    with pytest.raises(ProjectRegistryError, match="Equitify"):
        registry.register(
            ProjectRecord(
                id="equitify",
                name="Equitify Machine",
                root_path=str(tmp_path / "synthetic-equitify-name"),
            )
        )


def test_registry_separation_happy_path(tmp_path: Path):
    registry = ProjectRegistry(tmp_path / "projects.yaml")
    root = tmp_path / "app"
    root.mkdir()
    registry.register(
        ProjectRecord(id="app", name="App", root_path=str(root))
    )
    store = TaskStore(tmp_path / "workspace")
    task = store.create(
        {
            "id": "t-app",
            "title": "Work",
            "description": "On registered project",
            "project_id": "app",
            "task_type": "feature",
            "complexity": "normal",
            "risk_level": "medium",
        }
    )
    assert registry.require(task.project_id).id == "app"
