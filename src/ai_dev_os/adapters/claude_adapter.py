"""Claude manual-handoff adapter."""

from __future__ import annotations

from ..models import ModelRole
from .base import ManualHandoffAdapter


class ClaudeAdapter(ManualHandoffAdapter):
    role = ModelRole.CLAUDE
    display_name = "Claude"
