"""Atomic persistence helpers for orchestration artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def atomic_write_yaml(path: Path, payload: dict[str, Any]) -> None:
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    atomic_write_text(path, text)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, text)
