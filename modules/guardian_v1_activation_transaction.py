"""Offline-only activation transaction primitive.

Not connected to the Guardian operator socket or GUI. Call only when the monitor
is stopped and the installation is explicitly taken out of service.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

from modules.guardian_v1_activation_backup import prepare_activation_backup, ActivationBackupError


class ActivationTransactionError(ValueError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sync_dir(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def activate_offline(active_path: str | Path, candidate_path: str | Path,
                     backup_path: str | Path, *,
                     expected_active_sha256: str,
                     expected_candidate_sha256: str,
                     offline_authorization: str) -> dict[str, Any]:
    """Atomically replace YAML with validated candidate, with verified backup.

    The literal authorization is an API guard, NOT proof that a monitor is stopped.
    The caller must independently enforce exclusive ownership of the installation.
    Never expose this method to an operator socket without that interlock.
    """
    if offline_authorization != "OFFLINE_MONITOR_STOPPED":
        raise ActivationTransactionError("Offline authorization required")
    active, candidate, backup = [Path(p).expanduser().absolute()
                                 for p in (active_path, candidate_path, backup_path)]
    if any(p.is_symlink() for p in (active, candidate, backup)):
        raise ActivationTransactionError("Symlinks forbidden")
    try:
        evidence = prepare_activation_backup(
            active, candidate, backup,
            expected_active_sha256=expected_active_sha256,
            expected_candidate_sha256=expected_candidate_sha256)
    except (OSError, ValueError) as exc:
        raise ActivationTransactionError("Backup preflight failed") from exc

    original = backup.read_bytes()
    proposed = candidate.read_bytes()
    if _digest(original) != expected_active_sha256 or _digest(proposed) != expected_candidate_sha256:
        raise ActivationTransactionError("Files changed after backup")
    temporary: Path | None = None
    replaced = False
    try:
        fd, name = tempfile.mkstemp(prefix=".guardian-activation-", dir=active.parent)
        temporary = Path(name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(proposed)
            stream.flush()
            os.fsync(stream.fileno())
        if _digest(active.read_bytes()) != expected_active_sha256:
            raise ActivationTransactionError("Active YAML changed before replacement")
        if _digest(candidate.read_bytes()) != expected_candidate_sha256:
            raise ActivationTransactionError("Candidate changed before replacement")
        os.replace(temporary, active)
        replaced = True
        _sync_dir(active.parent)
        if _digest(active.read_bytes()) != expected_candidate_sha256:
            raise ActivationTransactionError("Post-activation verification failed")
    except BaseException as exc:
        if replaced:
            # Rollback uses independently verified backup bytes.
            fd, name = tempfile.mkstemp(prefix=".guardian-rollback-", dir=active.parent)
            rollback_temp = Path(name)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(rollback_temp, active)
                _sync_dir(active.parent)
                if _digest(active.read_bytes()) != expected_active_sha256:
                    raise ActivationTransactionError("CRITICAL: rollback verification failed") from exc
            finally:
                rollback_temp.unlink(missing_ok=True)
        raise ActivationTransactionError("Activation failed; rollback attempted if replaced") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "activated_on_disk": True,
        "runtime_restarted": False,
        "commissioning_authorized": False,
        "hardware_commands": 0,
        "backup_verified": True,
        "active_sha256": expected_candidate_sha256,
        "previous_sha256": expected_active_sha256,
        "candidate_identity": evidence["candidate_identity"],
        "changed_fields": evidence["changed_fields"],
    }
