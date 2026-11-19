"""Offline, fail-closed staging of proposed Guardian installation YAML.

This module NEVER edits active YAML, LaunchAgents, commissioning, or hardware.
It is intentionally not exposed through the running operator socket.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import yaml

from modules.guardian_v1_setup_config import read_installation, validate_changes


class StagingError(ValueError):
    pass


def stage_configuration(active_path: str | Path, changes: Mapping[str, Any], *,
                        expected_sha256: str, destination: str | Path) -> dict[str, Any]:
    """Validate and create a NEW candidate file, never overwrite anything.

    expected_sha256 binds the request to the exact original file bytes, avoiding
    stale proposals. Destination must not exist and must share the active file's
    directory, preventing accidental replacement of unrelated files.
    """
    active = Path(active_path).expanduser().resolve(strict=True)
    dest = Path(destination).expanduser().absolute()
    if dest.parent.resolve() != active.parent or dest == active:
        raise StagingError("Candidate must be a distinct file beside active configuration")
    if dest.exists() or dest.is_symlink():
        raise StagingError("Candidate already exists; refusing to overwrite")
    raw = active.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise StagingError("Active configuration changed since review")
    current = read_installation(active)
    candidate = validate_changes(current, changes)
    # A staging artifact is not an authorization or a request to activate.
    encoded = yaml.safe_dump(candidate, sort_keys=False, allow_unicode=True).encode("utf-8")
    # Exclusive create prevents overwriting, including symlinks. The candidate
    # may contain endpoint settings, so keep it private to the current user.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(dest, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {
        "staged": True,
        "activated": False,
        "commissioning_authorized": False,
        "candidate_path": str(dest),
        "original_sha256": digest,
        "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
        "changed_fields": sorted(f"{s}.{k}" for s, fields in changes.items() for k in fields),
    }


def configuration_sha256(active_path: str | Path) -> str:
    return hashlib.sha256(Path(active_path).read_bytes()).hexdigest()
