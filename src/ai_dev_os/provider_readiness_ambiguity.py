"""Round 4D1.1 — executable identity, wrappers, and ambiguity resolution."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from .fingerprints import fingerprint
from .provider_readiness_constants import (
    AMBIGUITY_RESOLUTION_SCHEMA_VERSION,
    EXECUTABLE_IDENTITY_POLICY_VERSION,
    EXECUTABLE_TRUST_POLICY_VERSION,
    LOGICAL_INSTALLATION_POLICY_VERSION,
    WRAPPER_READ_LIMIT,
)
from .provider_readiness_discovery import (
    ExecutableCandidate,
    hash_executable,
    sanitize_executable_location,
)
from .safe_policy import PolicyError, assert_not_equitify_blob

# Dynamic / unsafe wrapper patterns — contents treated as data; never executed.
# Argument forwarding (%*, %1) is allowed when the launch target itself is static.
_DYNAMIC_WRAPPER_RE = re.compile(
    r"(%~[^\sdpnfxaz0-9]*[^\sdpnfxaz0-9]|`|\$\(|\$\{|"
    r"\beval\b|"
    r"\bcmd\s+/c\b|\bpowershell\b.*-command|\binvoke-expression\b|"
    r"\bstart\s+/b\b|\bxargs\b)",
    re.IGNORECASE,
)

# Env-var path composition beyond %~dp0 / %~dp0.
_DYNAMIC_PATH_ENV_RE = re.compile(
    r"%(?! ~dp0)[A-Za-z_][A-Za-z0-9_]*%",
    re.IGNORECASE,
)

# Static relative launch patterns in .cmd/.bat
_CMD_DP0_TARGET_RE = re.compile(
    r'"?%~dp0([^"&\r\n]+)"?',
    re.IGNORECASE,
)
_CMD_QUOTED_REL_RE = re.compile(
    r'(?:^|\s)"((?:\.\\|\./|\.\.\\|\.\./)[^"\r\n]+)"',
    re.IGNORECASE | re.MULTILINE,
)
_POSIX_REL_EXEC_RE = re.compile(
    r'(?:^|\s)(?:"|\')?(\./[^\s\'"]+|\$\(dirname\s+"?\$0"?\)/[^\s\'"]+)',
    re.MULTILINE,
)


class AmbiguityClassification(str, Enum):
    SAME_BINARY_DUPLICATE_PATH = "same_binary_duplicate_path"
    SAME_BINARY_MULTIPLE_ALIASES = "same_binary_multiple_aliases"
    WRAPPER_AND_TARGET = "wrapper_and_target"
    VERSION_MANAGER_SHIM = "version_manager_shim"
    PACKAGE_MANAGER_SHIM = "package_manager_shim"
    APPLICATION_LAUNCHER = "application_launcher"
    STALE_PATH_ENTRY = "stale_path_entry"
    BROKEN_EXECUTABLE = "broken_executable"
    UNSUPPORTED_VERSION_DUPLICATE = "unsupported_version_duplicate"
    DISTINCT_INSTALLATIONS_SAME_VERSION = "distinct_installations_same_version"
    DISTINCT_INSTALLATIONS_DIFFERENT_VERSIONS = "distinct_installations_different_versions"
    TRUSTED_AND_UNTRUSTED_CANDIDATES = "trusted_and_untrusted_candidates"
    MULTIPLE_TRUSTED_CANDIDATES = "multiple_trusted_candidates"
    UNRESOLVED_PROVENANCE = "unresolved_provenance"
    UNSUPPORTED_WRAPPER = "unsupported_wrapper"
    INVALID_CANDIDATE_RECORD = "invalid_candidate_record"


class AutoCollapseRule(str, Enum):
    AC_SAME_TARGET_01 = "AC-SAME-TARGET-01"
    AC_SAME_FP_PROV_01 = "AC-SAME-FP-PROV-01"
    AC_EXCLUDE_BROKEN_01 = "AC-EXCLUDE-BROKEN-01"
    AC_EXCLUDE_UNTRUSTED_01 = "AC-EXCLUDE-UNTRUSTED-01"
    AC_WRAPPER_TARGET_01 = "AC-WRAPPER-TARGET-01"
    AC_DUP_DISCOVERY_01 = "AC-DUP-DISCOVERY-01"


class FileKind(str, Enum):
    EXE = "exe"
    CMD = "cmd"
    BAT = "bat"
    PS1 = "ps1"
    EXTENSIONLESS = "extensionless"
    SYMLINK = "symlink"
    OTHER = "other"
    MISSING = "missing"


class WrapperType(str, Enum):
    NONE = "none"
    CMD_WRAPPER = "cmd_wrapper"
    BAT_WRAPPER = "bat_wrapper"
    PS1_WRAPPER = "ps1_wrapper"
    POSIX_SCRIPT = "posix_script"
    PACKAGE_MANAGER_SHIM = "package_manager_shim"
    VERSION_MANAGER_SHIM = "version_manager_shim"
    APP_LAUNCHER = "app_launcher"
    SYMLINK_ALIAS = "symlink_alias"
    UNSUPPORTED = "unsupported"


@dataclass
class EnrichedCandidate:
    candidate_id: str
    provider_id: str
    path: str
    basename: str
    normalized_path: str
    real_target_path: str | None
    file_kind: str
    file_size: int | None
    mtime_ns: int | None
    fingerprint: str | None
    wrapper_type: str
    wrapper_target: str | None
    wrapper_contents_hash: str | None
    wrapper_supported: bool
    installation_mechanism: str
    provenance: str
    trust_status: str
    trust_notes: str
    executable_status: str
    path_rank: int | None
    discovery_methods: list[str]
    sanitized_location: str
    classification: str
    cli_version: str | None = None
    compatibility_status: str | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """Sanitized view — no full private path."""
        return {
            "basename": self.basename,
            "candidate_id": self.candidate_id,
            "classification": self.classification,
            "cli_version": self.cli_version,
            "compatibility_status": self.compatibility_status,
            "discovery_methods": list(self.discovery_methods),
            "evidence_ids": list(self.evidence_ids),
            "executable_status": self.executable_status,
            "file_kind": self.file_kind,
            "file_size": self.file_size,
            "fingerprint": self.fingerprint,
            "fingerprint_prefix": (self.fingerprint or "")[:12] or None,
            "installation_mechanism": self.installation_mechanism,
            "path_rank": self.path_rank,
            "provenance": self.provenance,
            "sanitized_location": self.sanitized_location,
            "trust_notes": self.trust_notes,
            "trust_status": self.trust_status,
            "wrapper_supported": self.wrapper_supported,
            "wrapper_target_label": (
                sanitize_executable_location(self.wrapper_target)
                if self.wrapper_target
                else None
            ),
            "wrapper_type": self.wrapper_type,
        }


@dataclass
class LogicalInstallation:
    logical_installation_id: str
    provider_id: str
    candidate_ids: list[str]
    canonical_target_label: str
    target_fingerprint: str | None
    cli_version: str | None
    installation_mechanism: str
    provenance: str
    trust_status: str
    compatibility_status: str | None
    aliases: list[str]
    wrappers: list[str]
    path_ranks: list[int]
    selected_invocation_candidate_id: str | None
    equivalence_evidence: list[str]
    ambiguity_status: str
    collapse_rule_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AmbiguityResolutionResult:
    provider_id: str
    schema_version: str
    identity_policy_version: str
    logical_policy_version: str
    trust_policy_version: str
    candidates: list[EnrichedCandidate]
    logical_installations: list[LogicalInstallation]
    resolved: bool
    selected_candidate_id: str | None
    selected_path: str | None
    selected_fingerprint: str | None
    collapse_rule_id: str | None
    requires_operator_selection: bool
    rejected_candidate_ids: list[str]
    rejection_reasons: dict[str, str]
    evidence_ids: list[str]
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "collapse_rule_id": self.collapse_rule_id,
            "candidates": [c.to_public_dict() for c in self.candidates],
            "evidence_ids": list(self.evidence_ids),
            "identity_policy_version": self.identity_policy_version,
            "logical_installations": [li.to_dict() for li in self.logical_installations],
            "logical_policy_version": self.logical_policy_version,
            "note": self.note,
            "provider_id": self.provider_id,
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "rejection_reasons": dict(self.rejection_reasons),
            "requires_operator_selection": self.requires_operator_selection,
            "resolved": self.resolved,
            "schema_version": self.schema_version,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_fingerprint": self.selected_fingerprint,
            "selected_location_label": (
                sanitize_executable_location(self.selected_path)
                if self.selected_path
                else None
            ),
            "trust_policy_version": self.trust_policy_version,
            "audit_events": list(self.audit_events),
        }


def _new_candidate_id(provider_id: str, path: str) -> str:
    digest = hashlib.sha256(f"{provider_id}|{path}".encode("utf-8")).hexdigest()[:12]
    return f"cand_{digest}"


def _new_evidence_id(kind: str) -> str:
    return f"evid_{kind}_{uuid4().hex[:10]}"


def normalize_path_key(path: str | Path) -> str:
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    text = str(resolved)
    if os.name == "nt":
        return os.path.normcase(text)
    return text


def detect_file_kind(path: Path) -> FileKind:
    if not path.exists():
        return FileKind.MISSING
    try:
        if path.is_symlink():
            return FileKind.SYMLINK
    except OSError:
        return FileKind.OTHER
    suffix = path.suffix.lower()
    if suffix == ".exe":
        return FileKind.EXE
    if suffix == ".cmd":
        return FileKind.CMD
    if suffix == ".bat":
        return FileKind.BAT
    if suffix == ".ps1":
        return FileKind.PS1
    if suffix == "":
        return FileKind.EXTENSIONLESS
    return FileKind.OTHER


def _path_mechanism_hints(path: Path) -> tuple[str, WrapperType | None]:
    parts_lower = [p.lower() for p in path.parts]
    joined = "/".join(parts_lower)
    if "windowsapps" in parts_lower:
        return "app_execution_alias", WrapperType.SYMLINK_ALIAS
    if any(x in joined for x in ("/npm/", "\\npm\\", "nodejs", "yarn", "pnpm", "bun")):
        if path.suffix.lower() in {".cmd", ".ps1", ".bat"} or path.name.endswith(".CMD"):
            return "package_manager_shim", WrapperType.PACKAGE_MANAGER_SHIM
    if any(x in joined for x in ("scoop", "chocolatey", "choco")):
        return "package_manager_shim", WrapperType.PACKAGE_MANAGER_SHIM
    if any(x in joined for x in ("nvm", "asdf", "pyenv", "fnm", "volta")):
        return "version_manager_shim", WrapperType.VERSION_MANAGER_SHIM
    if "programs" in parts_lower and path.suffix.lower() in {".cmd", ".bat"}:
        return "application_launcher", WrapperType.APP_LAUNCHER
    return "unknown", None


def read_wrapper_text(path: Path, *, limit: int = WRAPPER_READ_LIMIT) -> tuple[str | None, str | None]:
    """Return (text, contents_hash) or (None, None). Never executes contents."""
    try:
        if not path.is_file():
            return None, None
        raw = path.read_bytes()[:limit]
        digest = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8", errors="replace")
        return text, digest
    except OSError:
        return None, None


def wrapper_is_dynamic(text: str) -> bool:
    if not text:
        return False
    if _DYNAMIC_WRAPPER_RE.search(text):
        return True
    # Allow %~dp0; reject other %ENV% path composition.
    without_dp0 = re.sub(r"%~dp0", "", text, flags=re.IGNORECASE)
    if re.search(r"%[A-Za-z_][A-Za-z0-9_]*%", without_dp0):
        return True
    return False


def parse_static_wrapper_target(path: Path, text: str) -> str | None:
    """Deterministically parse a static relative target; never execute text."""
    if not text or wrapper_is_dynamic(text):
        return None
    parent = path.parent
    suffix = path.suffix.lower()

    candidates: list[Path] = []
    if suffix in {".cmd", ".bat"}:
        for match in _CMD_DP0_TARGET_RE.finditer(text):
            rel = match.group(1).strip().strip('"')
            # Skip batch argument expansions that are not paths
            if not rel or rel.startswith("%"):
                continue
            candidates.append((parent / rel).resolve() if True else parent / rel)
        for match in _CMD_QUOTED_REL_RE.finditer(text):
            rel = match.group(1).strip()
            candidates.append(parent / rel)
        # Common Cursor / CLI pattern: call sibling extensionless or .exe
        stem = path.stem
        for sibling_name in (stem, f"{stem}.exe", f"{stem}.js"):
            sibling = parent / sibling_name
            try:
                if sibling.exists() and sibling.resolve() != path.resolve():
                    if stem.lower() in text.lower() or sibling_name.lower() in text.lower():
                        candidates.append(sibling)
            except OSError:
                continue
        # Also accept "%~dp0stem" without quotes already covered; ensure stem.exe
        for match in re.finditer(rf"%~dp0{re.escape(stem)}(?:\.exe)?", text, re.IGNORECASE):
            rel = match.group(0).replace("%~dp0", "").replace("%~DP0", "")
            if rel:
                candidates.append(parent / rel)
    elif suffix == ".ps1":
        # Only accept simple Join-Path $PSScriptRoot 'name' patterns
        m = re.search(
            r"Join-Path\s+\$PSScriptRoot\s+['\"]([^'\"]+)['\"]",
            text,
            re.IGNORECASE,
        )
        if m:
            candidates.append(parent / m.group(1))
        if wrapper_is_dynamic(text):
            return None
    else:
        # POSIX / extensionless scripts
        for match in _POSIX_REL_EXEC_RE.finditer(text):
            rel = match.group(1)
            if rel.startswith("$(dirname"):
                # dirname "$0"/foo → parent/foo
                inner = rel.split(")/", 1)
                if len(inner) == 2:
                    candidates.append(parent / inner[1])
            elif rel.startswith("./"):
                candidates.append(parent / rel[2:])
        # Shebang node cli.js style
        m = re.search(r'(?:node|nodejs)\s+"?([^"\s]+\.js)"?', text, re.IGNORECASE)
        if m:
            candidates.append(parent / m.group(1))

    for cand in candidates:
        try:
            assert_not_equitify_blob(str(cand))
            resolved = cand.resolve()
            assert_not_equitify_blob(str(resolved))
            if resolved.exists() and resolved != path.resolve():
                return str(resolved)
        except (OSError, PolicyError):
            continue
    return None


def classify_wrapper(path: Path) -> tuple[WrapperType, str | None, str | None, bool]:
    """Return wrapper_type, target_path, contents_hash, supported."""
    kind = detect_file_kind(path)
    mechanism_hint, hint_type = _path_mechanism_hints(path)

    try:
        if path.is_symlink():
            target = str(path.resolve())
            assert_not_equitify_blob(target)
            return WrapperType.SYMLINK_ALIAS, target, None, True
    except (OSError, PolicyError):
        return WrapperType.UNSUPPORTED, None, None, False

    if kind in {FileKind.CMD, FileKind.BAT, FileKind.PS1, FileKind.EXTENSIONLESS, FileKind.OTHER}:
        text, contents_hash = read_wrapper_text(path)
        if text is None:
            return WrapperType.NONE, None, None, True
        # Binary .exe should not reach here often; if high NUL ratio skip
        if text.count("\x00") > 10:
            return WrapperType.NONE, None, contents_hash, True
        if kind == FileKind.EXE:
            return WrapperType.NONE, None, contents_hash, True

        if wrapper_is_dynamic(text):
            wtype = hint_type or WrapperType.UNSUPPORTED
            if wtype is WrapperType.NONE:
                wtype = WrapperType.UNSUPPORTED
            return WrapperType.UNSUPPORTED, None, contents_hash, False

        target = parse_static_wrapper_target(path, text)
        if kind is FileKind.CMD:
            wtype = hint_type or WrapperType.CMD_WRAPPER
            if wtype is WrapperType.APP_LAUNCHER:
                pass
            elif hint_type in {
                WrapperType.PACKAGE_MANAGER_SHIM,
                WrapperType.VERSION_MANAGER_SHIM,
            }:
                wtype = hint_type
            else:
                wtype = WrapperType.CMD_WRAPPER
            return wtype, target, contents_hash, target is not None or not text.strip()
        if kind is FileKind.BAT:
            return WrapperType.BAT_WRAPPER, target, contents_hash, target is not None
        if kind is FileKind.PS1:
            return WrapperType.PS1_WRAPPER, target, contents_hash, target is not None
        # extensionless / other scripts
        if text.lstrip().startswith("#!") or "node" in text[:200].lower():
            return WrapperType.POSIX_SCRIPT, target, contents_hash, True
        return WrapperType.NONE, None, contents_hash, True

    return WrapperType.NONE, None, None, True


def _executable_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        if not path.is_file() and not path.is_symlink():
            return "broken"
        # readable?
        with path.open("rb") as fh:
            fh.read(1)
        return "present"
    except OSError:
        return "unreadable"


def enrich_candidate(
    raw: ExecutableCandidate,
    *,
    provider_id: str,
    path_rank: int | None = None,
) -> EnrichedCandidate:
    path = Path(raw.path)
    kind = detect_file_kind(path)
    status = _executable_status(path)
    size = None
    mtime = None
    try:
        st = path.stat()
        size = int(st.st_size)
        mtime = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    except OSError:
        pass

    real_target = None
    try:
        real_target = str(path.resolve())
        assert_not_equitify_blob(real_target)
    except (OSError, PolicyError):
        real_target = None

    wrapper_type, wrapper_target, wrapper_hash, wrapper_ok = classify_wrapper(path)
    mechanism_hint, _ = _path_mechanism_hints(path)
    if wrapper_type is WrapperType.NONE:
        installation_mechanism = "standalone_binary" if kind is FileKind.EXE else mechanism_hint
        if kind is FileKind.EXTENSIONLESS:
            installation_mechanism = "standalone_binary"
    else:
        installation_mechanism = wrapper_type.value

    methods = [m for m in (raw.resolution_method or "").split("+") if m]
    trust_status = "trusted" if raw.trusted and status == "present" else "untrusted"
    if status in {"missing", "broken", "unreadable"}:
        trust_status = "untrusted"

    classification = AmbiguityClassification.UNRESOLVED_PROVENANCE.value
    if status == "missing":
        classification = AmbiguityClassification.STALE_PATH_ENTRY.value
    elif status in {"broken", "unreadable"}:
        classification = AmbiguityClassification.BROKEN_EXECUTABLE.value
    elif wrapper_type is WrapperType.UNSUPPORTED:
        classification = AmbiguityClassification.UNSUPPORTED_WRAPPER.value
    elif not raw.trusted:
        classification = AmbiguityClassification.TRUSTED_AND_UNTRUSTED_CANDIDATES.value

    evid = _new_evidence_id("cand")
    return EnrichedCandidate(
        candidate_id=_new_candidate_id(provider_id, raw.path),
        provider_id=provider_id,
        path=raw.path,
        basename=raw.basename,
        normalized_path=normalize_path_key(raw.path),
        real_target_path=real_target,
        file_kind=kind.value if isinstance(kind, FileKind) else str(kind),
        file_size=size,
        mtime_ns=mtime,
        fingerprint=raw.fingerprint or hash_executable(raw.path),
        wrapper_type=wrapper_type.value,
        wrapper_target=wrapper_target,
        wrapper_contents_hash=wrapper_hash,
        wrapper_supported=wrapper_ok,
        installation_mechanism=installation_mechanism,
        provenance=raw.resolution_method,
        trust_status=trust_status,
        trust_notes=raw.trust_notes,
        executable_status=status,
        path_rank=path_rank,
        discovery_methods=methods,
        sanitized_location=raw.sanitized_location or sanitize_executable_location(raw.path),
        classification=classification,
        evidence_ids=[evid],
    )


def _logical_id(provider_id: str, target_fp: str | None, target_path: str | None) -> str:
    payload = {
        "provider_id": provider_id,
        "target_fingerprint": target_fp,
        "target_normalized": normalize_path_key(target_path) if target_path else None,
        "policy": LOGICAL_INSTALLATION_POLICY_VERSION,
    }
    return f"logi_{fingerprint(payload)[:16]}"


def _target_key(c: EnrichedCandidate) -> str:
    """Identity key for collapse: prefer wrapper target, else real path."""
    if c.wrapper_target:
        return normalize_path_key(c.wrapper_target)
    if c.real_target_path:
        return normalize_path_key(c.real_target_path)
    return c.normalized_path


def _target_fingerprint_for(c: EnrichedCandidate, by_norm: dict[str, EnrichedCandidate]) -> str | None:
    if c.wrapper_target:
        key = normalize_path_key(c.wrapper_target)
        if key in by_norm and by_norm[key].fingerprint:
            return by_norm[key].fingerprint
        return hash_executable(c.wrapper_target)
    return c.fingerprint


def resolve_ambiguity(
    provider_id: str,
    raw_candidates: Sequence[ExecutableCandidate],
    *,
    path_order: Sequence[str] | None = None,
) -> AmbiguityResolutionResult:
    """Normalize candidates into logical installations; auto-collapse only under rule IDs."""
    events: list[dict[str, Any]] = []
    evidence: list[str] = []
    rejected: dict[str, str] = {}

    # PATH rank map (informational)
    rank_map: dict[str, int] = {}
    if path_order:
        for idx, p in enumerate(path_order):
            rank_map[normalize_path_key(p)] = idx

    enriched: list[EnrichedCandidate] = []
    seen_norm: dict[str, EnrichedCandidate] = {}
    for raw in raw_candidates:
        rank = rank_map.get(normalize_path_key(raw.path))
        c = enrich_candidate(raw, provider_id=provider_id, path_rank=rank)
        events.append(
            {
                "event_type": "candidate_discovered",
                "message": f"candidate {c.candidate_id}",
                "provider_id": provider_id,
                "details": {"candidate_id": c.candidate_id, "file_kind": c.file_kind},
            }
        )
        if c.wrapper_type not in {WrapperType.NONE.value}:
            events.append(
                {
                    "event_type": "wrapper_inspected",
                    "message": f"wrapper {c.wrapper_type}",
                    "provider_id": provider_id,
                    "details": {
                        "candidate_id": c.candidate_id,
                        "supported": c.wrapper_supported,
                        "has_target": bool(c.wrapper_target),
                    },
                }
            )
            if c.wrapper_target:
                events.append(
                    {
                        "event_type": "target_resolved",
                        "message": "static wrapper target resolved",
                        "provider_id": provider_id,
                        "details": {"candidate_id": c.candidate_id},
                    }
                )
        if c.fingerprint:
            events.append(
                {
                    "event_type": "candidate_fingerprinted",
                    "message": "fingerprint computed",
                    "provider_id": provider_id,
                    "details": {
                        "candidate_id": c.candidate_id,
                        "fingerprint_prefix": c.fingerprint[:12],
                    },
                }
            )
        evidence.extend(c.evidence_ids)
        # Deduplicate identical normalized paths (AC-DUP-DISCOVERY-01 precursor)
        if c.normalized_path in seen_norm:
            existing = seen_norm[c.normalized_path]
            for m in c.discovery_methods:
                if m not in existing.discovery_methods:
                    existing.discovery_methods.append(m)
            existing.provenance = "+".join(sorted(set(existing.discovery_methods)))
            existing.classification = AmbiguityClassification.SAME_BINARY_DUPLICATE_PATH.value
            continue
        seen_norm[c.normalized_path] = c
        enriched.append(c)

    enriched.sort(key=lambda x: (x.normalized_path, x.candidate_id))
    by_norm = {c.normalized_path: c for c in enriched}

    # Same-directory wrapper/target heuristic (e.g. cursor.cmd + cursor).
    for c in list(enriched):
        if c.wrapper_target:
            continue
        if c.file_kind not in {FileKind.CMD.value, FileKind.BAT.value}:
            continue
        stem = Path(c.path).stem.lower()
        parent = normalize_path_key(Path(c.path).parent)
        text, _ = read_wrapper_text(Path(c.path))
        if not text or wrapper_is_dynamic(text):
            # Still allow sibling link when only arg-forwarding dynamics exist and sibling matches.
            if not text:
                continue
        for other in enriched:
            if other.candidate_id == c.candidate_id:
                continue
            if normalize_path_key(Path(other.path).parent) != parent:
                continue
            other_stem = Path(other.path).stem.lower()
            other_name = Path(other.path).name.lower()
            if other_stem == stem or other_name == stem:
                if stem in text.lower() or other_name in text.lower() or f"%~dp0{stem}" in text.lower():
                    c.wrapper_target = other.path
                    c.wrapper_supported = True
                    if c.wrapper_type in {WrapperType.UNSUPPORTED.value, WrapperType.NONE.value}:
                        c.wrapper_type = WrapperType.CMD_WRAPPER.value
                    c.classification = AmbiguityClassification.WRAPPER_AND_TARGET.value
                    other.classification = AmbiguityClassification.WRAPPER_AND_TARGET.value
                    events.append(
                        {
                            "event_type": "target_resolved",
                            "message": "same-directory wrapper/target linked",
                            "provider_id": provider_id,
                            "details": {
                                "wrapper_id": c.candidate_id,
                                "target_id": other.candidate_id,
                            },
                        }
                    )
                    break

    # Classify wrapper/target relationships among set
    for c in enriched:
        if c.wrapper_target:
            tkey = normalize_path_key(c.wrapper_target)
            if tkey in by_norm:
                c.classification = AmbiguityClassification.WRAPPER_AND_TARGET.value
                by_norm[tkey].classification = AmbiguityClassification.WRAPPER_AND_TARGET.value
            elif c.wrapper_supported:
                c.classification = AmbiguityClassification.WRAPPER_AND_TARGET.value
            else:
                c.classification = AmbiguityClassification.UNSUPPORTED_WRAPPER.value
        elif c.wrapper_type == WrapperType.PACKAGE_MANAGER_SHIM.value:
            c.classification = AmbiguityClassification.PACKAGE_MANAGER_SHIM.value
        elif c.wrapper_type == WrapperType.VERSION_MANAGER_SHIM.value:
            c.classification = AmbiguityClassification.VERSION_MANAGER_SHIM.value
        elif c.wrapper_type == WrapperType.APP_LAUNCHER.value and c.wrapper_target:
            c.classification = AmbiguityClassification.APPLICATION_LAUNCHER.value
        elif c.wrapper_type == WrapperType.SYMLINK_ALIAS.value:
            c.classification = AmbiguityClassification.SAME_BINARY_MULTIPLE_ALIASES.value
        events.append(
            {
                "event_type": "candidate_classified",
                "message": c.classification,
                "provider_id": provider_id,
                "details": {"candidate_id": c.candidate_id},
            }
        )

    # Partition valid vs rejected
    valid: list[EnrichedCandidate] = []
    for c in enriched:
        if c.executable_status == "missing":
            rejected[c.candidate_id] = "stale_path_entry"
            continue
        if c.executable_status in {"broken", "unreadable"}:
            rejected[c.candidate_id] = "broken_executable"
            continue
        if c.trust_status != "trusted":
            rejected[c.candidate_id] = f"untrusted:{c.trust_notes}"
            continue
        if c.wrapper_type == WrapperType.UNSUPPORTED.value and not c.wrapper_target:
            # Keep as visible but not a selectable distinct install if others exist
            rejected[c.candidate_id] = "unsupported_wrapper"
            continue
        valid.append(c)

    collapse_rule: str | None = None
    selected: EnrichedCandidate | None = None
    requires_selection = False
    note = ""

    # Group by underlying target key
    groups: dict[str, list[EnrichedCandidate]] = {}
    for c in valid:
        groups.setdefault(_target_key(c), []).append(c)

    # Rule AC-DUP-DISCOVERY-01 already applied via seen_norm
    if len(enriched) >= 1 and len(seen_norm) == 1 and len(raw_candidates) > 1:
        collapse_rule = AutoCollapseRule.AC_DUP_DISCOVERY_01.value

    # Rule AC-EXCLUDE-BROKEN / UNTRUSTED
    if not valid and enriched:
        note = "no_trusted_candidate"
    elif len(groups) == 1:
        only_key = next(iter(groups))
        members = groups[only_key]
        # Same underlying target
        collapse_rule = collapse_rule or AutoCollapseRule.AC_SAME_TARGET_01.value
        # Prefer non-wrapper binary as invocation candidate; else lowest path_rank; else stable id
        non_wrappers = [
            m
            for m in members
            if m.wrapper_type in {WrapperType.NONE.value, WrapperType.SYMLINK_ALIAS.value}
            or m.file_kind == FileKind.EXE.value
        ]
        pool = non_wrappers or members
        pool_sorted = sorted(
            pool,
            key=lambda m: (
                m.path_rank if m.path_rank is not None else 10_000,
                0 if m.file_kind == FileKind.EXE.value else 1,
                m.candidate_id,
            ),
        )
        selected = pool_sorted[0]
        # If wrappers point at target, strengthen rule
        if any(m.wrapper_target for m in members) and any(
            normalize_path_key(m.wrapper_target) == only_key
            for m in members
            if m.wrapper_target
        ):
            collapse_rule = AutoCollapseRule.AC_WRAPPER_TARGET_01.value
        # Same fingerprint check
        fps = { _target_fingerprint_for(m, by_norm) for m in members }
        fps.discard(None)
        if len(fps) == 1:
            if collapse_rule == AutoCollapseRule.AC_SAME_TARGET_01.value:
                collapse_rule = AutoCollapseRule.AC_SAME_FP_PROV_01.value
        note = "ambiguity_collapsed_to_single_logical_installation"
    elif len(valid) == 1:
        selected = valid[0]
        if rejected:
            if any(r.startswith("untrusted") or r == "unsupported_wrapper" for r in rejected.values()):
                collapse_rule = AutoCollapseRule.AC_EXCLUDE_UNTRUSTED_01.value
            else:
                collapse_rule = AutoCollapseRule.AC_EXCLUDE_BROKEN_01.value
        else:
            collapse_rule = AutoCollapseRule.AC_SAME_TARGET_01.value
        note = "single_trusted_candidate"
    elif len(groups) > 1:
        # Distinct trusted installations
        requires_selection = True
        # Refine classifications
        fps = []
        for key, members in groups.items():
            fp = _target_fingerprint_for(members[0], by_norm)
            fps.append(fp)
        for c in valid:
            c.classification = AmbiguityClassification.MULTIPLE_TRUSTED_CANDIDATES.value
        note = "distinct_trusted_installations_require_operator_selection"
        events.append(
            {
                "event_type": "ambiguity_retained",
                "message": note,
                "provider_id": provider_id,
                "details": {"logical_group_count": len(groups)},
            }
        )
    else:
        note = "no_valid_candidates"

    # When we excluded down from multiple enriched to one group via rejects
    if selected is None and len(groups) == 0 and rejected and enriched:
        note = "no_trusted_candidate"

    logical_installations: list[LogicalInstallation] = []
    if requires_selection:
        for key, members in sorted(groups.items(), key=lambda kv: kv[0]):
            fp = _target_fingerprint_for(members[0], by_norm)
            inv = sorted(members, key=lambda m: m.candidate_id)[0]
            lid = _logical_id(provider_id, fp, key)
            li = LogicalInstallation(
                logical_installation_id=lid,
                provider_id=provider_id,
                candidate_ids=[m.candidate_id for m in members],
                canonical_target_label=sanitize_executable_location(key),
                target_fingerprint=fp,
                cli_version=None,
                installation_mechanism=members[0].installation_mechanism,
                provenance=",".join(sorted({m.provenance for m in members})),
                trust_status="trusted",
                compatibility_status=None,
                aliases=[m.sanitized_location for m in members],
                wrappers=[
                    m.candidate_id
                    for m in members
                    if m.wrapper_type != WrapperType.NONE.value
                ],
                path_ranks=[m.path_rank for m in members if m.path_rank is not None],
                selected_invocation_candidate_id=inv.candidate_id,
                equivalence_evidence=[e for m in members for e in m.evidence_ids],
                ambiguity_status="requires_selection",
                collapse_rule_id=None,
            )
            logical_installations.append(li)
            events.append(
                {
                    "event_type": "logical_installation_created",
                    "message": lid,
                    "provider_id": provider_id,
                    "details": {"candidate_ids": li.candidate_ids},
                }
            )
    elif selected is not None:
        # One logical installation from all valid (and optionally note rejected)
        members = list(groups.get(_target_key(selected), [selected]))
        # Include wrappers that collapse into this target
        for c in valid:
            if _target_key(c) == _target_key(selected) and c not in members:
                members.append(c)
        fp = _target_fingerprint_for(selected, by_norm)
        lid = _logical_id(provider_id, fp, _target_key(selected))
        li = LogicalInstallation(
            logical_installation_id=lid,
            provider_id=provider_id,
            candidate_ids=[m.candidate_id for m in members],
            canonical_target_label=sanitize_executable_location(_target_key(selected)),
            target_fingerprint=fp,
            cli_version=None,
            installation_mechanism=selected.installation_mechanism,
            provenance=selected.provenance,
            trust_status="trusted",
            compatibility_status=None,
            aliases=[m.sanitized_location for m in members],
            wrappers=[
                m.candidate_id
                for m in members
                if m.wrapper_type != WrapperType.NONE.value
            ],
            path_ranks=[m.path_rank for m in members if m.path_rank is not None],
            selected_invocation_candidate_id=selected.candidate_id,
            equivalence_evidence=evidence[:],
            ambiguity_status="collapsed" if len(members) > 1 or collapse_rule else "single",
            collapse_rule_id=collapse_rule,
        )
        logical_installations.append(li)
        events.append(
            {
                "event_type": "logical_installation_created",
                "message": lid,
                "provider_id": provider_id,
                "details": {"candidate_ids": li.candidate_ids},
            }
        )
        if collapse_rule and len(members) > 1:
            events.append(
                {
                    "event_type": "candidates_collapsed",
                    "message": collapse_rule,
                    "provider_id": provider_id,
                    "details": {
                        "rule_id": collapse_rule,
                        "selected_candidate_id": selected.candidate_id,
                    },
                }
            )

    resolved = selected is not None and not requires_selection
    return AmbiguityResolutionResult(
        provider_id=provider_id,
        schema_version=AMBIGUITY_RESOLUTION_SCHEMA_VERSION,
        identity_policy_version=EXECUTABLE_IDENTITY_POLICY_VERSION,
        logical_policy_version=LOGICAL_INSTALLATION_POLICY_VERSION,
        trust_policy_version=EXECUTABLE_TRUST_POLICY_VERSION,
        candidates=enriched,
        logical_installations=logical_installations,
        resolved=resolved,
        selected_candidate_id=selected.candidate_id if selected else None,
        selected_path=selected.path if selected else None,
        selected_fingerprint=(
            _target_fingerprint_for(selected, by_norm) if selected else None
        ),
        collapse_rule_id=collapse_rule,
        requires_operator_selection=requires_selection,
        rejected_candidate_ids=sorted(rejected.keys()),
        rejection_reasons=rejected,
        evidence_ids=evidence,
        audit_events=events,
        note=note,
    )
