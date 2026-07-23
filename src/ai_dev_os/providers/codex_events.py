"""Codex JSONL event normalization (Round 4D1.3) — never persists raw transcripts by default."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ..provider_models import FailureClass, ProviderResultStatus
from ..provider_readiness_constants import CODEX_EVENT_NORMALIZATION_SCHEMA_VERSION


@dataclass
class CodexEventSummary:
    event_class: str
    ordinal: int
    safe_excerpt: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodexNormalizedResult:
    schema_version: str
    provider_result_status: str
    failure_class: str
    event_summaries: list[CodexEventSummary] = field(default_factory=list)
    event_counts: dict[str, int] = field(default_factory=dict)
    final_safe_message: str | None = None
    usage: dict[str, Any] | None = None
    truncated: bool = False
    incomplete_turn: bool = False
    malformed_event_count: int = 0
    unexpected_eof: bool = False
    raw_jsonl_persisted: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_result_status": self.provider_result_status,
            "failure_class": self.failure_class,
            "event_summaries": [e.to_dict() for e in self.event_summaries],
            "event_counts": dict(self.event_counts),
            "final_safe_message": self.final_safe_message,
            "usage": self.usage,
            "truncated": self.truncated,
            "incomplete_turn": self.incomplete_turn,
            "malformed_event_count": self.malformed_event_count,
            "unexpected_eof": self.unexpected_eof,
            "raw_jsonl_persisted": self.raw_jsonl_persisted,
            "notes": list(self.notes),
        }


_CLASS_BY_TYPE = {
    "thread.started": "thread_session_started",
    "session.started": "thread_session_started",
    "turn.started": "turn_started",
    "agent.message": "agent_message",
    "message": "agent_message",
    "item.completed": "agent_message",
    "command.request": "command_request",
    "command.execution": "command_request",
    "command.result": "command_result",
    "file.change": "file_change",
    "file_change": "file_change",
    "approval.request": "approval_request",
    "usage": "usage_record",
    "token_usage": "usage_record",
    "turn.completed": "turn_completed",
    "error": "error_event",
    "interrupted": "interrupted_process",
}


def _classify(obj: dict[str, Any]) -> str:
    raw = str(obj.get("type") or obj.get("event") or obj.get("kind") or "").strip()
    key = raw.lower()
    if key in _CLASS_BY_TYPE:
        return _CLASS_BY_TYPE[key]
    # Soft substring matches for evolving Codex schemas.
    if "error" in key:
        return "error_event"
    if "usage" in key:
        return "usage_record"
    if "approval" in key:
        return "approval_request"
    if "command" in key and "result" in key:
        return "command_result"
    if "command" in key:
        return "command_request"
    if "file" in key:
        return "file_change"
    if "turn" in key and "complete" in key:
        return "turn_completed"
    if "turn" in key and "start" in key:
        return "turn_started"
    if "thread" in key or "session" in key:
        return "thread_session_started"
    if "message" in key or "agent" in key:
        return "agent_message"
    if "interrupt" in key:
        return "interrupted_process"
    return "unknown_event"


def _safe_excerpt(obj: dict[str, Any], *, limit: int = 160) -> str:
    for key in ("message", "text", "content", "summary", "error"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            cleaned = val.replace("\n", " ").strip()
            if len(cleaned) > limit:
                return cleaned[:limit] + "...[truncated]"
            return cleaned
    return ""


def _redact_secrets(text: str) -> str:
    import re

    return re.sub(
        r"(?i)(token|api[_-]?key|authorization|bearer)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        text or "",
    )


def normalize_codex_jsonl(
    text: str,
    *,
    stream_ended: bool = True,
    max_events: int = 200,
    max_chars: int = 200_000,
) -> CodexNormalizedResult:
    """Normalize Codex JSONL into safe summaries. Does not persist raw JSONL."""
    notes: list[str] = ["raw_jsonl_not_persisted_by_default"]
    truncated = False
    body = text or ""
    if len(body) > max_chars:
        body = body[:max_chars]
        truncated = True
        notes.append("input_truncated_by_char_limit")

    summaries: list[CodexEventSummary] = []
    counts: dict[str, int] = {}
    malformed = 0
    usage: dict[str, Any] | None = None
    final_msg: str | None = None
    saw_turn_completed = False
    saw_error = False
    saw_interrupted = False
    auth_fail = False
    quota_fail = False
    sandbox_fail = False
    network_fail = False
    permission_fail = False

    lines = body.splitlines()
    if len(lines) > max_events:
        lines = lines[:max_events]
        truncated = True
        notes.append("events_truncated_by_count_limit")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            malformed += 1
            summaries.append(
                CodexEventSummary(
                    event_class="malformed_event",
                    ordinal=idx,
                    safe_excerpt="malformed_json_line",
                )
            )
            counts["malformed_event"] = counts.get("malformed_event", 0) + 1
            continue
        if not isinstance(obj, dict):
            malformed += 1
            counts["malformed_event"] = counts.get("malformed_event", 0) + 1
            continue

        event_class = _classify(obj)
        counts[event_class] = counts.get(event_class, 0) + 1
        excerpt = _redact_secrets(_safe_excerpt(obj))
        summaries.append(
            CodexEventSummary(event_class=event_class, ordinal=idx, safe_excerpt=excerpt)
        )

        if event_class == "turn_completed":
            saw_turn_completed = True
        if event_class == "error_event":
            saw_error = True
            low = excerpt.lower()
            if "auth" in low or "login" in low or "unauthorized" in low:
                auth_fail = True
            if "quota" in low or "usage limit" in low or "rate limit" in low:
                quota_fail = True
            if "sandbox" in low:
                sandbox_fail = True
            if "network" in low or "dns" in low or "connection" in low:
                network_fail = True
            if "permission" in low or "denied" in low:
                permission_fail = True
        if event_class == "interrupted_process":
            saw_interrupted = True
        if event_class == "usage_record":
            usage = {
                k: obj.get(k)
                for k in ("input_tokens", "output_tokens", "total_tokens", "credits")
                if k in obj
            } or {"reported": True}
        if event_class == "agent_message" and excerpt:
            final_msg = excerpt

    unexpected_eof = bool(lines) and stream_ended is False
    incomplete = (not saw_turn_completed) and bool(summaries) and not saw_error

    if auth_fail:
        status, fail = ProviderResultStatus.FAILED.value, FailureClass.PROVIDER_ERROR.value
        notes.append("authentication_failure_detected")
    elif quota_fail:
        status, fail = ProviderResultStatus.FAILED.value, FailureClass.PROVIDER_ERROR.value
        notes.append("quota_or_usage_limit_detected")
    elif sandbox_fail or permission_fail:
        status, fail = ProviderResultStatus.REJECTED.value, FailureClass.POLICY_REJECTED.value
        notes.append("sandbox_or_permission_blocked")
    elif network_fail:
        status, fail = ProviderResultStatus.FAILED.value, FailureClass.PROVIDER_ERROR.value
        notes.append("network_policy_or_connectivity_failure")
    elif saw_interrupted:
        status, fail = ProviderResultStatus.CANCELLED.value, FailureClass.CANCELLED.value
    elif malformed and not summaries:
        status, fail = ProviderResultStatus.ERROR.value, FailureClass.MALFORMED_OUTPUT.value
    elif incomplete or unexpected_eof:
        status, fail = ProviderResultStatus.ERROR.value, FailureClass.MALFORMED_OUTPUT.value
        notes.append("incomplete_turn_or_unexpected_eof")
    elif saw_error:
        status, fail = ProviderResultStatus.FAILED.value, FailureClass.PROVIDER_ERROR.value
    elif saw_turn_completed or (summaries and not saw_error):
        status, fail = ProviderResultStatus.SUCCESS.value, FailureClass.NONE.value
    else:
        status, fail = ProviderResultStatus.ERROR.value, FailureClass.MALFORMED_OUTPUT.value

    return CodexNormalizedResult(
        schema_version=CODEX_EVENT_NORMALIZATION_SCHEMA_VERSION,
        provider_result_status=status,
        failure_class=fail,
        event_summaries=summaries[:max_events],
        event_counts=counts,
        final_safe_message=final_msg,
        usage=usage,
        truncated=truncated,
        incomplete_turn=incomplete,
        malformed_event_count=malformed,
        unexpected_eof=unexpected_eof,
        raw_jsonl_persisted=False,
        notes=notes,
    )


def build_future_codex_exec_argv(
    *,
    pinned_executable: str,
    worktree_path: str,
    sandbox_mode: str,
    prompt_text: str | None = None,
    json_mode: bool = True,
    ephemeral: bool = True,
) -> list[str] | None:
    """Construct future Round 4D2 argv shape for tests/docs.

    Returns None when ``prompt_text`` is provided — readiness must never build
    live prompt argv. Callers that need the shape for documentation should pass
    ``prompt_text=None`` and append a placeholder only in synthetic fixtures.
    """
    if prompt_text is not None:
        return None
    argv = [pinned_executable, "exec"]
    if json_mode:
        argv.append("--json")
    if ephemeral:
        argv.append("--ephemeral")
    argv.extend(["--sandbox", sandbox_mode, "-C", worktree_path])
    # Prompt intentionally omitted — Round 4D2 authorization required to add it.
    return argv
