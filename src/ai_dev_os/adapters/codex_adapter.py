"""Codex manual-handoff adapter (independent review / second opinion)."""

from __future__ import annotations

from ..models import ModelRole
from .base import ManualHandoffAdapter


class CodexAdapter(ManualHandoffAdapter):
    role = ModelRole.CODEX
    display_name = "Codex"
