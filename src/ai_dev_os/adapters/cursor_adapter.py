"""Cursor manual-handoff adapter."""

from __future__ import annotations

from ..models import ModelRole
from .base import ManualHandoffAdapter


class CursorAdapter(ManualHandoffAdapter):
    role = ModelRole.CURSOR
    display_name = "Cursor"
