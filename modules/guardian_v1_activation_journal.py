"""Durable, offline activation journal. No runtime control or activation API."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile

class JournalError(ValueError):
    pass

STATES = ("PREPARED", "BACKUP_VERIFIED", "REPLACEMENT_WRITTEN", "VERIFIED", "RECONCILIATION_REQUIRED")
TRANSITIONS = {"PREPARED": {"BACKUP_VERIFIED"}, "BACKUP_VERIFIED": {"REPLACEMENT_WRITTEN"}, "REPLACEMENT_WRITTEN": {"VERIFIED", "RECONCILIATION_REQUIRED"}, "VERIFIED": {"RECONCILIATION_REQUIRED"}, "RECONCILIATION_REQUIRED": set()}

def _check_hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise JournalError("Invalid SHA-256")

def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def _load(path):
    if path.is_symlink() or not path.is_file():
        raise JournalError("Journal missing or symlink")
    obj = json.loads(path.read_text())
    if not isinstance(obj, dict) or obj.get("version") != 1 or obj.get("state") not in STATES:
        raise JournalError("Invalid journal")
    for key in ("previous_sha256", "candidate_sha256"):
        _check_hash(obj.get(key))
    if set(obj) != {"version", "state", "previous_sha256", "candidate_sha256"}:
        raise JournalError("Unexpected journal fields")
    return obj

def read_journal(path):
    obj = _load(Path(path))
    return {**obj, "activation_authorized": False, "commissioning_authorized": False, "arm_authorized": False}

def create_journal(path, *, previous_sha256, candidate_sha256):
    """Create a new journal exclusively. Caller must verify runtime is stopped."""
    _check_hash(previous_sha256); _check_hash(candidate_sha256)
    if previous_sha256 == candidate_sha256: raise JournalError("No configuration change")
    path = Path(path)
    if path.exists() or path.is_symlink(): raise JournalError("Journal already exists")
    data = {"version": 1, "state": "PREPARED", "previous_sha256": previous_sha256, "candidate_sha256": candidate_sha256}
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        _sync_dir(path.parent)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return read_journal(path)

def advance_journal(path, *, expected_state, next_state):
    """Atomic state write; requires external exclusive transaction lock."""
    path = Path(path)
    data = _load(path)
    if data["state"] != expected_state or next_state not in TRANSITIONS[data["state"]]:
        raise JournalError("Invalid or stale journal transition")
    data["state"] = next_state
    fd, tmpname = tempfile.mkstemp(prefix=".guardian-journal-", dir=path.parent)
    tmp = Path(tmpname)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        if _load(path)["state"] != expected_state:
            raise JournalError("Journal changed during transition")
        os.replace(tmp, path)
        _sync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)
    return read_journal(path)
