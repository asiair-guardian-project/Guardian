"""Read-only, fail-closed audit of a staged activation's on-disk state.

No filesystem mutations; never grants permission to activate or ARM.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

class RecoveryAuditError(ValueError):
    pass

def _digest(path: Path) -> str | None:
    if path.is_symlink():
        raise RecoveryAuditError("Symlink is not allowed")
    if not path.exists():
        return None
    if not path.is_file():
        raise RecoveryAuditError("Expected a regular file")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit_activation_state(active_path, candidate_path, backup_path, *,
                           expected_previous_sha256, expected_candidate_sha256):
    """Classify bytes only; no assertion about runtime, durability or commissioning."""
    paths = [Path(p).expanduser().absolute() for p in
             (active_path, candidate_path, backup_path)]
    if len(set(paths)) != 3 or len({p.parent for p in paths}) != 1:
        raise RecoveryAuditError("Paths must be distinct sibling files")
    if any(not isinstance(h, str) or len(h) != 64 or
           any(c not in "0123456789abcdef" for c in h)
           for h in (expected_previous_sha256, expected_candidate_sha256)):
        raise RecoveryAuditError("Expected SHA-256 hashes are required")
    active, candidate, backup = map(_digest, paths)
    if active is None:
        state = "ACTIVE_MISSING"
    elif active == expected_previous_sha256 and backup is None:
        state = "NOT_STARTED"
    elif active == expected_previous_sha256 and backup == expected_previous_sha256:
        state = "BACKUP_PRESENT_ACTIVE_UNCHANGED"
    elif active == expected_candidate_sha256 and backup == expected_previous_sha256:
        state = "REPLACEMENT_ON_DISK_REQUIRES_RUNTIME_RECONCILIATION"
    elif active == expected_previous_sha256 and backup != expected_previous_sha256:
        state = "BACKUP_MISMATCH"
    else:
        state = "AMBIGUOUS_REQUIRES_MANUAL_RECOVERY"
    if candidate != expected_candidate_sha256:
        state = "CANDIDATE_MISSING_OR_CHANGED"
    return {"state": state, "activation_authorized": False,
            "commissioning_authorized": False, "arm_authorized": False,
            "runtime_verified": False, "hardware_commands": 0,
            "requires_operator_review": state != "NOT_STARTED"}
