"""Safe multi-candidate provider executable discovery (Round 4D1)."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .provider_discovery import PROVIDER_EXECUTABLE_BASENAMES, assert_provider_executable_allowed
from .provider_readiness_constants import PROBE_TIMEOUT_DEFAULT
from .provider_readiness_models import DiscoveryStatus
from .safe_policy import PolicyError, assert_no_shell_metacharacters, assert_not_equitify_blob, filter_environment

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class ExecutableCandidate:
    path: str
    basename: str
    resolution_method: str
    fingerprint: str | None = None
    trusted: bool = True
    trust_notes: str = ""
    sanitized_location: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "basename": self.basename,
            "fingerprint": self.fingerprint,
            "path_sanitized": self.sanitized_location,
            "resolution_method": self.resolution_method,
            "trust_notes": self.trust_notes,
            "trusted": self.trusted,
        }


@dataclass
class DiscoveryResult:
    provider_id: str
    status: DiscoveryStatus
    candidates: list[ExecutableCandidate] = field(default_factory=list)
    selected: ExecutableCandidate | None = None
    selected_rule: str = "none"
    note: str = ""
    duplicate_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "duplicate_count": self.duplicate_count,
            "note": self.note,
            "provider_id": self.provider_id,
            "selected": self.selected.to_dict() if self.selected else None,
            "selected_rule": self.selected_rule,
            "status": self.status.value,
        }


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def sanitize_executable_location(path: str | Path) -> str:
    """Return a privacy-preserving location class, not the full PATH."""
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    parent = resolved.parent
    name = resolved.name
    home = Path.home()
    try:
        if home in resolved.parents or resolved == home:
            rel = resolved.relative_to(home)
            return f"user_home/{rel.parent.as_posix()}/{name}" if rel.parent.as_posix() != "." else f"user_home/{name}"
    except (ValueError, OSError):
        pass
    # Collapse to drive/root class without listing PATH entries.
    parts = resolved.parts
    if len(parts) >= 2:
        root = parts[0].rstrip("\\/")
        return f"path_entry/{root}/{name}"
    return f"path_entry/{name}"


def hash_executable(path: str | Path) -> str | None:
    p = Path(path)
    try:
        if not p.is_file() or p.is_symlink():
            # Still hash symlink target if it is a regular file after resolve.
            try:
                resolved = p.resolve(strict=True)
            except OSError:
                return None
            if not resolved.is_file():
                return None
            p = resolved
        h = hashlib.sha256()
        with p.open("rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _is_trusted_candidate(path: Path) -> tuple[bool, str]:
    try:
        assert_not_equitify_blob(str(path))
    except PolicyError as exc:
        return False, str(exc)
    try:
        resolved = path.resolve()
    except OSError as exc:
        return False, f"resolve_failed:{exc}"
    # Reject if path string itself looks like equitify after resolve.
    try:
        assert_not_equitify_blob(str(resolved))
    except PolicyError as exc:
        return False, str(exc)
    if not resolved.exists():
        return False, "missing"
    return True, "ok"


def _add_candidate(
    bucket: dict[str, ExecutableCandidate],
    *,
    path: str,
    basename: str,
    method: str,
) -> None:
    try:
        key = str(Path(path).resolve())
    except OSError:
        key = str(Path(path))
    if key in bucket:
        existing = bucket[key]
        if method not in existing.resolution_method:
            existing.resolution_method = f"{existing.resolution_method}+{method}"
        return
    trusted, notes = _is_trusted_candidate(Path(path))
    bucket[key] = ExecutableCandidate(
        path=key,
        basename=basename,
        resolution_method=method,
        fingerprint=hash_executable(key) if trusted else None,
        trusted=trusted,
        trust_notes=notes,
        sanitized_location=sanitize_executable_location(key),
    )


def _which_candidates(names: Sequence[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name in sorted(set(names)):
        hit = shutil.which(name)
        if hit:
            found.append((hit, name))
    return found


def _where_exe_candidates(names: Sequence[str], timeout: float = PROBE_TIMEOUT_DEFAULT) -> list[tuple[str, str]]:
    if platform.system().lower() != "windows":
        return []
    where = shutil.which("where.exe") or shutil.which("where")
    if not where:
        return []
    results: list[tuple[str, str]] = []
    for name in sorted(set(names)):
        try:
            assert_no_shell_metacharacters([where, name])
            completed = subprocess.run(
                [where, name],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
                env=filter_environment(None),
            )
        except (OSError, subprocess.TimeoutExpired, PolicyError):
            continue
        for line in (completed.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            results.append((line, name))
    return results


def _get_command_candidates(names: Sequence[str], timeout: float = PROBE_TIMEOUT_DEFAULT) -> list[tuple[str, str]]:
    """Windows Get-Command Source path when powershell is available."""
    if platform.system().lower() != "windows":
        return []
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return []
    results: list[tuple[str, str]] = []
    for name in sorted(set(names)):
        # Safe: name is from allowlist basenames only; no user free text.
        script = (
            f"$c = Get-Command -Name {name!s} -ErrorAction SilentlyContinue; "
            "if ($c) { $c.Source }"
        )
        # Only allow known provider basenames without metacharacters.
        if re.search(r"[|&;`$<>]", name):
            continue
        try:
            assert_no_shell_metacharacters([ps, "-NoProfile", "-Command", script])
            completed = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
                env=filter_environment(None),
            )
        except (OSError, subprocess.TimeoutExpired, PolicyError):
            continue
        for line in (completed.stdout or "").splitlines():
            line = line.strip()
            if line:
                results.append((line, name))
    return results


def discover_executable_candidates(
    provider_id: str,
    *,
    configured_path: str | None = None,
    path_env: str | None = None,
    enable_where: bool = True,
    enable_get_command: bool = True,
) -> DiscoveryResult:
    """Discover candidates without printing PATH or installing software."""
    if provider_id == "simulated":
        return DiscoveryResult(
            provider_id=provider_id,
            status=DiscoveryStatus.NOT_INSTALLED,
            note="simulated has no live CLI; not a live-smoke candidate",
            selected_rule="none",
        )

    allowed = PROVIDER_EXECUTABLE_BASENAMES.get(provider_id)
    if not allowed:
        return DiscoveryResult(
            provider_id=provider_id,
            status=DiscoveryStatus.PROBE_FAILED,
            note="unknown provider id",
        )

    # Optional PATH override for tests only (does not mutate process PATH permanently).
    old_path = None
    if path_env is not None:
        old_path = os.environ.get("PATH")
        os.environ["PATH"] = path_env

    bucket: dict[str, ExecutableCandidate] = {}
    try:
        if configured_path:
            try:
                assert_provider_executable_allowed(provider_id, configured_path)
                _add_candidate(
                    bucket,
                    path=configured_path,
                    basename=Path(configured_path).name,
                    method="configured",
                )
            except PolicyError as exc:
                return DiscoveryResult(
                    provider_id=provider_id,
                    status=DiscoveryStatus.EXECUTABLE_UNTRUSTED,
                    note=str(exc),
                )

        for hit, name in _which_candidates(sorted(allowed)):
            try:
                assert_provider_executable_allowed(provider_id, hit)
            except PolicyError:
                continue
            _add_candidate(bucket, path=hit, basename=name, method="python_which")

        if enable_where:
            for hit, name in _where_exe_candidates(sorted(allowed)):
                try:
                    assert_provider_executable_allowed(provider_id, hit)
                except PolicyError:
                    continue
                _add_candidate(bucket, path=hit, basename=Path(hit).name, method="where_exe")

        if enable_get_command:
            for hit, name in _get_command_candidates(sorted(allowed)):
                try:
                    assert_provider_executable_allowed(provider_id, hit)
                except PolicyError:
                    continue
                _add_candidate(bucket, path=hit, basename=Path(hit).name, method="get_command")
    finally:
        if path_env is not None:
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path

    candidates = sorted(bucket.values(), key=lambda c: (c.path.lower(), c.basename.lower()))
    trusted = [c for c in candidates if c.trusted]
    untrusted = [c for c in candidates if not c.trusted]

    if untrusted and not trusted:
        return DiscoveryResult(
            provider_id=provider_id,
            status=DiscoveryStatus.EXECUTABLE_UNTRUSTED,
            candidates=candidates,
            duplicate_count=len(candidates),
            note="all candidates failed trust checks",
            selected_rule="none",
        )

    if not trusted:
        status = DiscoveryStatus.NOT_INSTALLED
        note = "not found on PATH"
        if provider_id == "cursor":
            note = (
                "No safely detectable Cursor automation CLI on PATH; "
                "desktop app presence is not assumed"
            )
        return DiscoveryResult(
            provider_id=provider_id,
            status=status,
            candidates=candidates,
            note=note,
            selected_rule="none",
        )

    # Distinct fingerprints among trusted candidates.
    fingerprints = {c.fingerprint for c in trusted if c.fingerprint}
    distinct_paths = {c.path for c in trusted}

    if configured_path:
        try:
            cfg_key = str(Path(configured_path).resolve())
        except OSError:
            cfg_key = str(Path(configured_path))
        configured_hits = [c for c in trusted if c.path == cfg_key]
        if len(configured_hits) == 1:
            selected = configured_hits[0]
            return DiscoveryResult(
                provider_id=provider_id,
                status=DiscoveryStatus.INSTALLED,
                candidates=candidates,
                selected=selected,
                selected_rule="configured_override",
                duplicate_count=len(distinct_paths),
                note="configured path selected",
            )

    if len(distinct_paths) > 1:
        # Same content fingerprint across paths is still ambiguous for provenance.
        if len(fingerprints) > 1 or len(fingerprints) == 0 or len(distinct_paths) > 1:
            return DiscoveryResult(
                provider_id=provider_id,
                status=DiscoveryStatus.AMBIGUOUS_INSTALLATION,
                candidates=candidates,
                selected=None,
                selected_rule="none",
                duplicate_count=len(distinct_paths),
                note="multiple distinct executable candidates; no silent selection",
            )

    # Single trusted path (possibly rediscovered by multiple methods).
    selected = trusted[0]
    return DiscoveryResult(
        provider_id=provider_id,
        status=DiscoveryStatus.INSTALLED,
        candidates=candidates,
        selected=selected,
        selected_rule="single_candidate",
        duplicate_count=1,
        note="single trusted candidate",
    )
