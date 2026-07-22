"""Secret-pattern scanning with redaction (no secret persistence)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "api_key_assignment",
        re.compile(
            r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9\-_/+=]{16,}"
        ),
    ),
    (
        "bearer_token",
        re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_\.]{20,}"),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "aws_access_key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
    ),
]

PLACEHOLDER_SAFE = re.compile(
    r"(?i)(YOUR_API_KEY|REDACTED|CHANGEME|EXAMPLE_SECRET|xxx+|placeholder|<api[_-]?key>)"
)

BINARY_EXT = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".pyc", ".exe", ".dll"}
)


@dataclass
class SecretFinding:
    path: str
    rule: str
    line_number: int
    redacted_snippet: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "rule": self.rule,
            "line_number": self.line_number,
            "redacted_snippet": self.redacted_snippet,
        }


@dataclass
class SecretScanResult:
    findings: list[SecretFinding] = field(default_factory=list)
    files_examined: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def redact_secrets(text: str) -> str:
    """Replace likely secret material with [REDACTED] for sanitized reports."""
    out = text
    for _name, pattern in SECRET_RULES:
        out = pattern.sub("[REDACTED]", out)
    # Generic env-looking assignments
    out = re.sub(
        r"(?i)(password|token|secret|credential)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        out,
    )
    return out


def _is_placeholder_line(line: str) -> bool:
    return bool(PLACEHOLDER_SAFE.search(line))


def scan_text(path: str, text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _is_placeholder_line(line):
            continue
        for rule_name, pattern in SECRET_RULES:
            if pattern.search(line):
                findings.append(
                    SecretFinding(
                        path=path,
                        rule=rule_name,
                        line_number=i,
                        redacted_snippet=redact_secrets(line.strip())[:200],
                    )
                )
                break
    return findings


def scan_files(repo_root: Path, rel_paths: Iterable[str]) -> SecretScanResult:
    root = Path(repo_root)
    findings: list[SecretFinding] = []
    examined: list[str] = []
    for rel in rel_paths:
        norm = rel.replace("\\", "/")
        if norm.endswith("/") or any(norm.endswith(ext) for ext in BINARY_EXT):
            continue
        path = root / rel
        if not path.is_file():
            continue
        examined.append(norm)
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:4096]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
        findings.extend(scan_text(norm, text))
    return SecretScanResult(findings=findings, files_examined=sorted(set(examined)))
