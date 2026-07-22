"""Explicit validation for tasks, paths, plans, and lifecycle transitions."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath, PurePosixPath

from .models import (
    LIFECYCLE_TRANSITIONS,
    PLAN_TRANSITIONS,
    ApprovalRequirement,
    Complexity,
    Plan,
    PlanStatus,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
)


class ValidationError(ValueError):
    """Raised when a task or related artifact fails validation."""


REQUIRED_TASK_FIELDS = (
    "id",
    "title",
    "description",
    "project_id",
    "task_type",
    "complexity",
    "risk_level",
)


def _normalize_path_key(path_str: str) -> str:
    raw = path_str.strip().replace("/", "\\")
    try:
        p = PureWindowsPath(raw)
    except Exception:
        p = PurePosixPath(path_str.strip())
    return str(p).lower()


def is_path_under(path_str: str, root_str: str) -> bool:
    """Return True if path_str resolves under root_str (string-prefix safe for Windows)."""
    path_key = _normalize_path_key(path_str)
    root_key = _normalize_path_key(root_str).rstrip("\\")
    if path_key == root_key:
        return True
    return path_key.startswith(root_key + "\\")


def path_matches_prefix(path_str: str, prefix: str) -> bool:
    return is_path_under(path_str, prefix) or _normalize_path_key(path_str).startswith(
        _normalize_path_key(prefix)
    )


def validate_required_fields(data: dict) -> None:
    missing = [name for name in REQUIRED_TASK_FIELDS if not data.get(name)]
    if missing:
        raise ValidationError(f"Missing required task fields: {', '.join(missing)}")


def validate_enums(data: dict) -> None:
    try:
        TaskType(data["task_type"])
        Complexity(data["complexity"])
        RiskLevel(data["risk_level"])
        if "status" in data and data["status"] is not None:
            TaskStatus(data["status"])
    except (KeyError, ValueError) as exc:
        raise ValidationError(f"Invalid enum value: {exc}") from exc


def validate_transition(current: TaskStatus, new: TaskStatus) -> None:
    if current == new:
        return
    allowed = LIFECYCLE_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValidationError(
            f"Invalid lifecycle transition: {current.value} → {new.value}. "
            f"Allowed: {sorted(s.value for s in allowed) or 'none'}"
        )


def validate_no_illegal_jump(current: TaskStatus, new: TaskStatus) -> None:
    """Explicitly reject draft→completed and similar illegal jumps."""
    if current is TaskStatus.DRAFT and new is TaskStatus.COMPLETED:
        raise ValidationError("Illegal jump: draft → completed is not allowed")
    validate_transition(current, new)


def validate_task_paths(task: Task, project_root: str | None = None) -> None:
    for path in task.prohibited_paths:
        if not str(path).strip():
            raise ValidationError("Empty prohibited path is not allowed")
    for path in task.allowed_paths:
        if not str(path).strip():
            raise ValidationError("Empty allowed path is not allowed")
        for prohibited in task.prohibited_paths:
            if path_matches_prefix(path, prohibited):
                raise ValidationError(
                    f"Allowed path '{path}' conflicts with prohibited path '{prohibited}'"
                )
        if project_root and not is_path_under(path, project_root):
            # Relative allowed paths are OK; absolute ones must stay under project root.
            candidate = Path(path)
            if candidate.is_absolute() and not is_path_under(str(candidate), project_root):
                raise ValidationError(
                    f"Allowed path '{path}' is outside project root '{project_root}'"
                )


def validate_prohibited_absolute_paths(
    paths: list[str], prohibited_prefixes: list[str]
) -> None:
    for path in paths:
        for prefix in prohibited_prefixes:
            if path_matches_prefix(path, prefix):
                raise ValidationError(
                    f"Path '{path}' is prohibited (matches '{prefix}')"
                )


def validate_task_dict(data: dict) -> Task:
    if not isinstance(data, dict):
        raise ValidationError("Task payload must be a mapping")
    validate_required_fields(data)
    validate_enums(data)
    try:
        task = Task.from_dict(data)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid task payload: {exc}") from exc
    if not task.id.strip() or not task.title.strip() or not task.description.strip():
        raise ValidationError("id, title, and description must be non-empty")
    if not task.project_id.strip():
        raise ValidationError("project_id must be non-empty")
    validate_task_paths(task)
    return task


def apply_status_transition(task: Task, new_status: TaskStatus) -> Task:
    validate_no_illegal_jump(task.status, new_status)
    data = task.to_dict()
    data["status"] = new_status.value
    from .models import utc_now_iso

    data["updated_at"] = utc_now_iso()
    return Task.from_dict(data)


REQUIRED_PLAN_FIELDS = (
    "plan_id",
    "task_id",
    "project_id",
    "planner_agent",
    "starting_commit",
    "objective",
)


def validate_plan_transition(current: PlanStatus, new: PlanStatus) -> None:
    if current == new:
        return
    allowed = PLAN_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValidationError(
            f"Invalid plan transition: {current.value} → {new.value}. "
            f"Allowed: {sorted(s.value for s in allowed) or 'none'}"
        )


def validate_plan_dict(data: dict) -> Plan:
    if not isinstance(data, dict):
        raise ValidationError("Plan payload must be a mapping")
    missing = [name for name in REQUIRED_PLAN_FIELDS if not data.get(name)]
    if missing:
        raise ValidationError(f"Missing required plan fields: {', '.join(missing)}")
    try:
        if "status" in data and data["status"] is not None:
            PlanStatus(data["status"])
        if "approval_requirement" in data and data["approval_requirement"] is not None:
            ApprovalRequirement(data["approval_requirement"])
        if "risk_level" in data and data["risk_level"] is not None:
            RiskLevel(data["risk_level"])
        plan = Plan.from_dict(data)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid plan payload: {exc}") from exc
    if not plan.objective.strip():
        raise ValidationError("objective must be non-empty")
    if not plan.starting_commit.strip():
        raise ValidationError("starting_commit must be non-empty")
    if not plan.implementation_steps:
        raise ValidationError("implementation_steps must be non-empty")
    if not plan.testing_plan:
        raise ValidationError("testing_plan must be non-empty")
    if not plan.files_expected_to_change:
        raise ValidationError("files_expected_to_change must be non-empty")
    return plan
