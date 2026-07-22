"""Round 4C reporting version constants and fingerprint field sets."""

from __future__ import annotations

EVIDENCE_SCHEMA_VERSION = "4c.1"
REPORT_SCHEMA_VERSION = "4c.1"
REPORT_POLICY_VERSION = "4c.1"
RELEVANCE_POLICY_VERSION = "4c.1"
REDACTION_POLICY_VERSION = "4c.1"
RENDERER_VERSION = "4c.1"

# Fields excluded from semantic report fingerprint (volatile / rendering-only).
REPORT_FP_EXCLUDE: frozenset[str] = frozenset(
    {
        "generated_at",
        "rendered_paths",
        "show_metadata",
        "report_fingerprint",  # self-reference
    }
)

BANNED_EXECUTIVE_PHRASES: tuple[str, ...] = (
    "perfect",
    "fully secure",
    "production ready",
    "completely tested",
    "all good",
)

EQUITIFY_SENTINELS: tuple[str, ...] = (
    "equitify-machine",
    "equitify_machine",
    "equitify",
)
