"""Safe discovery and confined provider subprocess helpers (Round 3B)."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence

from .provider_models import InstallationStatus
from .safe_policy import (
    PolicyError,
    assert_no_shell_metacharacters,
    assert_not_equitify_blob,
    filter_environment,
)


DISCOVERY_TIMEOUT_DEFAULT = 5.0
DISCOVERY_TIMEOUT_MAX = 15.0
DISCOVERY_OUTPUT_LIMIT = 8192

# Basenames that may be resolved for discovery / future gated live.
PROVIDER_EXECUTABLE_BASENAMES: dict[str, frozenset[str]] = {
    "claude_code": frozenset({"claude", "claude.exe", "claude.cmd"}),
    "codex": frozenset({"codex", "codex.exe", "codex.cmd"}),
    "cursor": frozenset({"cursor", "cursor.exe", "cursor.cmd"}),
    "simulated": frozenset(),
}

DISCOVERY_ARGV_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    "claude_code": ("--version",),
    "codex": ("--version",),
    "cursor": ("--version",),
}

VERSION_LINE_RE = re.compile(r"v?\d+\.\d+(\.\d+)?", re.IGNORECASE)


def clamp_discovery_timeout(timeout: float | None) -> float:
    value = DISCOVERY_TIMEOUT_DEFAULT if timeout is None else float(timeout)
    if value <= 0:
        raise PolicyError("Discovery timeout must be positive")
    if value > DISCOVERY_TIMEOUT_MAX:
        raise PolicyError(
            f"Discovery timeout {value} exceeds hard ceiling {DISCOVERY_TIMEOUT_MAX}"
        )
    return value


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    clipped = raw[:limit].decode("utf-8", errors="replace")
    return clipped + "\n...[truncated]...", True


def assert_provider_executable_allowed(provider_id: str, executable: str | Path) -> str:
    assert_not_equitify_blob(str(executable), provider_id)
    base = Path(executable).name.lower()
    allowed = PROVIDER_EXECUTABLE_BASENAMES.get(provider_id, frozenset())
    if not allowed:
        raise PolicyError(f"Provider {provider_id} has no executable allowlist")
    if base not in allowed:
        raise PolicyError(
            f"Arbitrary or unsupported executable refused for {provider_id}: {base}"
        )
    assert_no_shell_metacharacters([str(executable)])
    return base


def resolve_provider_executable(
    provider_id: str,
    configured_path: str | None = None,
) -> tuple[str | None, InstallationStatus, str]:
    """Resolve executable without installing or broad filesystem search.

    Returns (path_or_none, status, note).
    """
    if provider_id == "simulated":
        return None, InstallationStatus.NOT_APPLICABLE, "simulated has no CLI"

    allowed = PROVIDER_EXECUTABLE_BASENAMES.get(provider_id)
    if not allowed:
        return None, InstallationStatus.AMBIGUOUS, "unknown provider id"

    if configured_path:
        try:
            assert_provider_executable_allowed(provider_id, configured_path)
        except PolicyError as exc:
            return None, InstallationStatus.ERROR, str(exc)
        path = Path(configured_path)
        if path.is_file():
            return str(path.resolve()), InstallationStatus.DETECTED, "configured path"
        return None, InstallationStatus.NOT_INSTALLED, "configured path missing"

    # Standard PATH lookup only — no recursive search.
    for name in sorted(allowed):
        found = shutil.which(name)
        if found:
            try:
                assert_provider_executable_allowed(provider_id, found)
            except PolicyError as exc:
                return None, InstallationStatus.ERROR, str(exc)
            return found, InstallationStatus.DETECTED, f"PATH lookup: {name}"

    return None, InstallationStatus.NOT_INSTALLED, "not found on PATH"


def parse_version_string(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = VERSION_LINE_RE.search(line)
        if match:
            return line[:200]
    return None


def run_discovery_command(
    executable: str,
    argv_tail: Sequence[str],
    *,
    timeout: float | None = None,
    output_limit: int = DISCOVERY_OUTPUT_LIMIT,
) -> dict[str, object]:
    """Run harmless version/help discovery only."""
    assert_not_equitify_blob(executable, *argv_tail)
    assert_no_shell_metacharacters([executable, *argv_tail])
    for token in argv_tail:
        if token not in ("--version", "--help", "-V", "-h", "version", "help"):
            raise PolicyError(f"Discovery argv token refused: {token!r}")
    timeout_s = clamp_discovery_timeout(timeout)
    argv = [executable, *argv_tail]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
            check=False,
            env=filter_environment(None),
        )
        stdout, stdout_trunc = _truncate(completed.stdout or "", output_limit)
        stderr, stderr_trunc = _truncate(completed.stderr or "", output_limit)
        return {
            "argv": argv,
            "exit_code": int(completed.returncode),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_trunc,
            "stderr_truncated": stderr_trunc,
            "timeout_status": False,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "version": parse_version_string(stdout) or parse_version_string(stderr),
            "error": None,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stdout, stdout_trunc = _truncate(stdout, output_limit)
        stderr, stderr_trunc = _truncate(stderr, output_limit)
        return {
            "argv": argv,
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_trunc,
            "stderr_truncated": stderr_trunc,
            "timeout_status": True,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "version": None,
            "error": f"Discovery timed out after {timeout_s}s",
        }
    except OSError as exc:
        return {
            "argv": argv,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "timeout_status": False,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "version": None,
            "error": f"Failed to spawn discovery process: {exc}",
        }


def discover_provider(
    provider_id: str,
    *,
    configured_path: str | None = None,
    timeout: float | None = None,
) -> dict[str, object]:
    """Safe discovery record for one provider."""
    if provider_id == "simulated":
        return {
            "provider_id": provider_id,
            "executable": None,
            "installation_status": InstallationStatus.NOT_APPLICABLE.value,
            "detected_version": "simulated-3b.1",
            "note": "simulated provider; no CLI discovery",
            "discovery_ran": False,
            "live_model_call": False,
        }

    exe, status, note = resolve_provider_executable(provider_id, configured_path)
    result: dict[str, object] = {
        "provider_id": provider_id,
        "executable": exe,
        "installation_status": status.value,
        "detected_version": None,
        "note": note,
        "discovery_ran": False,
        "live_model_call": False,
        "discovery": None,
    }
    if status is not InstallationStatus.DETECTED or not exe:
        # Cursor desktop without CLI stays ambiguous/manual.
        if provider_id == "cursor" and status is InstallationStatus.NOT_INSTALLED:
            result["installation_status"] = InstallationStatus.AMBIGUOUS.value
            result["note"] = (
                "No safely detectable Cursor automation CLI on PATH; "
                "desktop app presence is not assumed. Manual handoff remains available."
            )
        return result

    tail = DISCOVERY_ARGV_BY_PROVIDER.get(provider_id, ("--version",))
    discovery = run_discovery_command(exe, tail, timeout=timeout)
    result["discovery_ran"] = True
    result["discovery"] = discovery
    result["detected_version"] = discovery.get("version")
    if discovery.get("error") and not discovery.get("version"):
        result["note"] = str(discovery.get("error"))
        if provider_id == "cursor":
            result["installation_status"] = InstallationStatus.AMBIGUOUS.value
            result["note"] = (
                "Cursor executable detected but version/help discovery did not "
                "prove non-interactive agent support; treating as ambiguous."
            )
    return result
