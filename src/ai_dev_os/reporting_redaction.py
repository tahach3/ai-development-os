"""Fail-closed report redaction (Round 4C)."""

from __future__ import annotations

import re
from typing import Any

from .ci_secrets import redact_secrets
from .reporting_models import RedactionEvent, new_evidence_id

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ABS_PATH_RE = re.compile(r"(?i)(?:[A-Z]:\\|\\\\)[^\s\"']+")
PROMPT_MARKERS = ("system prompt", "raw prompt", "provider transcript")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def truncate_text(text: str, max_chars: int = 4000) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[: max_chars - 14] + "\n…[truncated]", True


def sanitize_text(text: str, *, field_path: str, events: list[RedactionEvent]) -> str:
    original = text
    out = strip_ansi(text)
    out = redact_secrets(out)
    if ABS_PATH_RE.search(out):
        out = ABS_PATH_RE.sub("[REDACTED_PATH]", out)
        events.append(
            RedactionEvent(
                event_id=new_evidence_id("rdx"),
                category="absolute_path",
                field_path=field_path,
                reason="Unrelated absolute path redacted",
            )
        )
    lowered = out.lower()
    for marker in PROMPT_MARKERS:
        if marker in lowered:
            out = "[REDACTED_PROVIDER_CONTENT]"
            events.append(
                RedactionEvent(
                    event_id=new_evidence_id("rdx"),
                    category="provider_content",
                    field_path=field_path,
                    reason=f"Blocked content matching {marker}",
                )
            )
            break
    if out != redact_secrets(original) and "secret" not in [e.category for e in events[-3:]]:
        if "[REDACTED]" in out and "[REDACTED]" not in original:
            events.append(
                RedactionEvent(
                    event_id=new_evidence_id("rdx"),
                    category="secret",
                    field_path=field_path,
                    reason="Secret pattern redacted",
                )
            )
    return out


def sanitize_structure(value: Any, *, field_path: str, events: list[RedactionEvent]) -> Any:
    if isinstance(value, str):
        return sanitize_text(value, field_path=field_path, events=events)
    if isinstance(value, list):
        return [
            sanitize_structure(v, field_path=f"{field_path}[{i}]", events=events)
            for i, v in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            k: sanitize_structure(v, field_path=f"{field_path}.{k}", events=events)
            for k, v in sorted(value.items(), key=lambda kv: kv[0])
        }
    return value
