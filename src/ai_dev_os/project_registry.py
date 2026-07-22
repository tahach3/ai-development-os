"""Project registry — refuse unregistered projects; no Equitify by default."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import ProjectRecord
from .validation import ValidationError, is_path_under, path_matches_prefix


EQUITIFY_SENTINELS = (
    "equitify-machine",
    "equitify_machine",
    "equitify",
)


class ProjectRegistryError(ValidationError):
    """Raised when project registration or lookup fails."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_registry_path() -> Path:
    return _repo_root() / "config" / "projects.yaml"


def example_registry_path() -> Path:
    return _repo_root() / "config" / "projects.example.yaml"


class ProjectRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_registry_path()
        self._projects: dict[str, ProjectRecord] = {}
        if self.path.exists():
            self.load()

    def load(self) -> None:
        with self.path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        projects = raw.get("projects") if isinstance(raw, dict) else None
        if projects is None:
            projects = []
        if not isinstance(projects, list):
            raise ProjectRegistryError("projects must be a list")
        loaded: dict[str, ProjectRecord] = {}
        for item in projects:
            if not isinstance(item, dict):
                raise ProjectRegistryError("Each project entry must be a mapping")
            record = ProjectRecord.from_dict(item)
            self._assert_not_equitify(record)
            loaded[record.id] = record
        self._projects = loaded

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"projects": [p.to_dict() for p in self._projects.values()]}
        with self.path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, sort_keys=False)

    @staticmethod
    def _assert_not_equitify(record: ProjectRecord) -> None:
        blob = " ".join(
            [
                record.id,
                record.name,
                record.root_path,
                str(record.metadata),
            ]
        ).lower()
        for sentinel in EQUITIFY_SENTINELS:
            if sentinel in blob.replace("\\", "/"):
                raise ProjectRegistryError(
                    "Equitify must not be registered until the user explicitly says: "
                    '"Connect the AI Development Operating System to Equitify."'
                )

    def list_projects(self) -> list[ProjectRecord]:
        return list(self._projects.values())

    def get(self, project_id: str) -> ProjectRecord:
        if project_id not in self._projects:
            raise ProjectRegistryError(
                f"Unregistered project refused: '{project_id}'. "
                "Register it first with register-project."
            )
        return self._projects[project_id]

    def require(self, project_id: str) -> ProjectRecord:
        record = self.get(project_id)
        if not record.active:
            raise ProjectRegistryError(f"Project '{project_id}' is inactive")
        return record

    def register(self, record: ProjectRecord, *, overwrite: bool = False) -> ProjectRecord:
        self._assert_not_equitify(record)
        if not record.id.strip():
            raise ProjectRegistryError("project id is required")
        if not record.name.strip():
            raise ProjectRegistryError("project name is required")
        root = Path(record.root_path)
        if not record.root_path.strip():
            raise ProjectRegistryError("root_path is required")
        # Normalize to absolute string for Windows-compatible storage.
        record.root_path = str(root.resolve()) if root.exists() else str(Path(record.root_path))
        if record.id in self._projects and not overwrite:
            raise ProjectRegistryError(f"Project already registered: {record.id}")
        self._projects[record.id] = record
        self.save()
        return record

    def ensure_path_allowed(
        self,
        project_id: str,
        path: str,
    ) -> None:
        record = self.require(project_id)
        for prefix in record.prohibited_path_prefixes:
            if path_matches_prefix(path, prefix):
                raise ProjectRegistryError(
                    f"Path '{path}' matches prohibited prefix '{prefix}' for project '{project_id}'"
                )
        if record.allowed_path_prefixes:
            if not any(path_matches_prefix(path, p) for p in record.allowed_path_prefixes):
                # Absolute paths outside allowed prefixes are refused; relative may be scoped later.
                if Path(path).is_absolute() and not is_path_under(path, record.root_path):
                    raise ProjectRegistryError(
                        f"Path '{path}' is outside allowed prefixes for project '{project_id}'"
                    )

    def resolve_root(self, project_id: str) -> Path:
        return Path(self.require(project_id).root_path)
