"""Offline, non-activating, fail-closed backup of Guardian installation YAML.

Creates an exclusive immutable-by-convention backup of the current YAML. Never
replaces active configuration, changes commissioning, or operates hardware.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from modules.guardian_v1_setup_config import read_installation, validate_changes
from modules.guardian_v1_configuration_identity import semantic_fingerprint


class ActivationBackupError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare_activation_backup(active_path: str | Path, candidate_path: str | Path,
                              backup_path: str | Path, *, expected_active_sha256: str,
                              expected_candidate_sha256: str) -> dict[str, Any]:
    """Prepare rollback bytes only; explicit hashes prevent stale review.

    This is NOT an activation permission. Backup must be a new file in the same
    directory. Candidate may change only the fields supported by setup validation.
    """
    supplied = [Path(p).expanduser().absolute() for p in (active_path, candidate_path, backup_path)]
    if any(p.is_symlink() for p in supplied):
        raise ActivationBackupError('Symlink paths are forbidden')
    active, candidate, backup = supplied
    if len(set(supplied)) != 3 or len({p.parent.resolve(strict=True) for p in supplied}) != 1:
        raise ActivationBackupError('All three paths must be distinct sibling files')
    if backup.exists() or backup.is_symlink():
        raise ActivationBackupError('Backup already exists')
    if not active.is_file() or not candidate.is_file():
        raise ActivationBackupError('Active and candidate must exist')
    original_bytes, candidate_bytes = active.read_bytes(), candidate.read_bytes()
    if _sha(original_bytes) != expected_active_sha256 or _sha(candidate_bytes) != expected_candidate_sha256:
        raise ActivationBackupError('Configuration changed since review')
    original, proposed = read_installation(active), read_installation(candidate)
    if set(original) != set(proposed):
        raise ActivationBackupError('Configuration sections differ')
    changes: dict[str, dict[str, Any]] = {}
    for section in original:
        before, after = original[section], proposed[section]
        if not isinstance(before, dict) or not isinstance(after, dict) or set(before) != set(after):
            raise ActivationBackupError('Configuration structure differs')
        fields = {k: after[k] for k in before if before[k] != after[k]}
        if fields:
            changes[section] = fields
    if not changes:
        raise ActivationBackupError('Candidate has no changes')
    if validate_changes(original, changes) != proposed:
        raise ActivationBackupError('Candidate contains unsupported changes')
    # Recheck the bytes immediately before writing the backup.
    if _sha(active.read_bytes()) != expected_active_sha256 or _sha(candidate.read_bytes()) != expected_candidate_sha256:
        raise ActivationBackupError('Configuration changed during review')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(backup, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(original_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        if _sha(backup.read_bytes()) != expected_active_sha256:
            raise ActivationBackupError('Backup verification failed')
        dirfd = os.open(active.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    return {
        'backup_verified': True,
        'active_unchanged': True,
        'candidate_unchanged': True,
        'activated': False,
        'commissioning_authorized': False,
        'hardware_commands': 0,
        'active_sha256': expected_active_sha256,
        'candidate_sha256': expected_candidate_sha256,
        'active_identity': semantic_fingerprint(original),
        'candidate_identity': semantic_fingerprint(proposed),
        'changed_fields': sorted(f'{section}.{key}' for section, fields in changes.items() for key in fields),
    }
