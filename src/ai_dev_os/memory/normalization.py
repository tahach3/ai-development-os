"""Versioned content normalization for shared memory.

Reuses Round 4A ``ci_secrets.scan_text`` for secret refusal. Does not alter
``ci_secrets`` behavior — memory policy is refuse-on-hit for durable content.
"""

from __future__ import annotations

import re
import unicodedata

from ai_dev_os.ci_secrets import scan_text

from .errors import MemorySecurityError, MemoryValidationError
from .versions import MEMORY_NORMALIZATION_VERSION

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_memory_content(content: str, *, path: str = "memory:content") -> str:
    """NFKC + trim + collapse whitespace + casefold for hash/search input.

    Original caller-supplied ``content`` should remain unchanged on the record;
    this returns the derived ``content_normalized`` value only.
    """
    if not isinstance(content, str):
        raise MemoryValidationError("content must be a string")
    if not content.strip():
        raise MemoryValidationError("content must be non-empty")

    # Fail closed before deriving a durable normalized form.
    refuse_secrets_in_text(content, path=path)

    nfkc = unicodedata.normalize("NFKC", content)
    collapsed = _WHITESPACE_RE.sub(" ", nfkc.strip())
    return collapsed.casefold()


def refuse_secrets_in_text(text: str, *, path: str = "memory:content") -> None:
    """Refuse secret-like material using existing ``ci_secrets`` rules.

    Exception messages never include the raw secret — only rule names.
    """
    findings = scan_text(path, text)
    if findings:
        rules = sorted({f.rule for f in findings})
        raise MemorySecurityError(
            "Secret pattern refused for durable memory "
            f"(rules={','.join(rules)}; normalization={MEMORY_NORMALIZATION_VERSION})"
        )


def normalization_version() -> str:
    return MEMORY_NORMALIZATION_VERSION
