"""Persistent isolated session records and lifecycle for Round 3A."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import yaml

from .execution_models import SessionRecord, SessionStatus
from .models import utc_now_iso
from .project_registry import ProjectRegistry, ProjectRegistryError
from .safe_policy import PolicyError, assert_not_equitify_blob
from .worktrees import (
    WorktreeError,
    create_session_worktree,
    read_head,
    remove_session_worktree,
    require_git_repo,
)


class SessionError(ValueError):
    """Raised for session lifecycle violations."""


_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class SessionStore:
    def __init__(
        self,
        workspace_root: Path | None = None,
        registry: ProjectRegistry | None = None,
    ) -> None:
        base = workspace_root or (_repo_root() / "workspace")
        self.workspace_root = base
        self.sessions_root = base / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self.registry = registry or ProjectRegistry()

    def _session_dir(self, session_id: str) -> Path:
        return self.sessions_root / session_id

    def _session_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.yaml"

    def exists(self, session_id: str) -> bool:
        return self._session_path(session_id).exists()

    def save(self, record: SessionRecord) -> Path:
        path = self._session_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(record.to_dict(), fh, sort_keys=False)
        return path

    def load(self, session_id: str) -> SessionRecord:
        path = self._session_path(session_id)
        if not path.exists():
            raise SessionError(f"Session not found: {session_id}")
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return SessionRecord.from_dict(data)

    def list_sessions(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        for path in sorted(self.sessions_root.glob("*/session.yaml")):
            with path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            records.append(SessionRecord.from_dict(data))
        return records

    def create(
        self,
        *,
        project_id: str,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> SessionRecord:
        try:
            project = self.registry.require(project_id)
        except ProjectRegistryError as exc:
            raise SessionError(str(exc)) from exc

        assert_not_equitify_blob(
            project.id, project.name, project.root_path, task_id or ""
        )

        sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        if not _SESSION_ID_RE.match(sid):
            raise SessionError(f"Invalid session_id: {sid}")
        if self.exists(sid):
            raise SessionError(f"Session already exists: {sid}")

        project_root = Path(project.root_path).resolve()
        try:
            require_git_repo(project_root)
            head = read_head(project_root)
        except WorktreeError as exc:
            raise SessionError(str(exc)) from exc

        worktree_path = self._session_dir(sid) / "worktree"
        try:
            created = create_session_worktree(
                project_root=project_root,
                worktree_path=worktree_path,
                commit=head,
                sessions_root=self.sessions_root,
            )
        except (WorktreeError, PolicyError) as exc:
            raise SessionError(str(exc)) from exc

        record = SessionRecord(
            session_id=sid,
            project_id=project.id,
            task_id=task_id,
            starting_commit=head,
            worktree_path=str(created),
            project_root=str(project_root),
            status=SessionStatus.ACTIVE,
        )
        self.save(record)
        return record

    def assert_immutable_identity(
        self,
        record: SessionRecord,
        *,
        project_id: str | None = None,
        starting_commit: str | None = None,
    ) -> None:
        if project_id is not None and project_id != record.project_id:
            raise SessionError(
                "Sessions cannot change project_id after creation"
            )
        if starting_commit is not None and starting_commit != record.starting_commit:
            raise SessionError(
                "Sessions cannot change starting_commit after creation"
            )

    def update_metadata(self, session_id: str, metadata: dict) -> SessionRecord:
        record = self.load(session_id)
        if record.status is SessionStatus.CLEANED_UP:
            raise SessionError(f"Session already cleaned up: {session_id}")
        # Refuse identity mutation via metadata smuggling
        for forbidden in ("project_id", "starting_commit", "session_id"):
            if forbidden in metadata:
                raise SessionError(
                    f"Cannot mutate {forbidden} via session metadata"
                )
        merged = dict(record.metadata)
        merged.update(metadata)
        record.metadata = merged
        record.updated_at = utc_now_iso()
        self.save(record)
        return record

    def cleanup(self, session_id: str) -> SessionRecord:
        record = self.load(session_id)
        if record.status is SessionStatus.CLEANED_UP:
            return record
        project_root = Path(record.project_root or self.registry.resolve_root(record.project_id))
        main_before = None
        try:
            main_before = read_head(project_root)
        except WorktreeError:
            main_before = None

        try:
            remove_session_worktree(
                project_root=project_root,
                worktree_path=Path(record.worktree_path),
            )
        except (WorktreeError, PolicyError) as exc:
            record.status = SessionStatus.FAILED
            record.updated_at = utc_now_iso()
            self.save(record)
            raise SessionError(str(exc)) from exc

        # Verify main checkout HEAD unchanged when readable.
        if main_before is not None:
            try:
                main_after = read_head(project_root)
                if main_after != main_before:
                    raise SessionError(
                        "Cleanup unexpectedly changed main checkout HEAD"
                    )
            except WorktreeError:
                pass

        record.status = SessionStatus.CLEANED_UP
        record.cleaned_up_at = utc_now_iso()
        record.updated_at = record.cleaned_up_at
        self.save(record)
        return record

    def require_active(self, session_id: str) -> SessionRecord:
        record = self.load(session_id)
        if record.status is SessionStatus.CLEANED_UP:
            raise SessionError(f"Session is cleaned up: {session_id}")
        if record.status is SessionStatus.FAILED:
            raise SessionError(f"Session is failed: {session_id}")
        return record
