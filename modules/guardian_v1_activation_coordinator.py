"""Fail-closed Phase C offline coordinator (no GUI/LaunchAgent control).

This is intentionally NOT an online activation API. It requires a separately
stopped monitor, exclusive lifetime lock, and a candidate whose monitor binding
matches the installed LaunchAgent. It never grants ARM or commissioning.
"""
from __future__ import annotations

from pathlib import Path
from modules.guardian_v1_activation_preflight import activation_preflight
from modules.guardian_v1_activation_interlock import inspect_monitor_stopped
from modules.guardian_v1_runtime_lock import offline_activation_lock
from modules.guardian_v1_activation_journal import create_journal, advance_journal
from modules.guardian_v1_activation_transaction import activate_offline
from modules.guardian_v1_activation_recovery import audit_activation_state
from modules.guardian_v1_setup_binding import MonitorBinding
from modules.guardian_v1_activation_safety import require_safe_recovery, inspect_launch_plist


class OfflineActivationRejected(RuntimeError):
    pass


def activate_stopped_monitor(*, active_path: str | Path, candidate_path: str | Path,
                             backup_path: str | Path, journal_path: str | Path,
                             runtime_lock_path: str | Path, binding: MonitorBinding,
                             confirmed: bool = False,
                             recovery_file=None, launch_plist=None, socket_path=None,
                             verify_stopped=inspect_monitor_stopped) -> dict:
    """One-way offline file activation. No restart, recovery or authorization.

    Caller must stop/disable LaunchAgent *outside* this function and ensure no
    unresolved incident. An existing journal blocks retries pending recovery.
    """
    if confirmed is True and not all((recovery_file, launch_plist, socket_path)):
        raise OfflineActivationRejected('Recovery file, LaunchAgent plist and operator socket are mandatory')
    if confirmed is not True:
        raise OfflineActivationRejected('Explicit operator confirmation required')
    active, candidate, backup, journal = (Path(p).expanduser().absolute() for p in
                                           (active_path, candidate_path, backup_path, journal_path))
    if len({active, candidate, backup, journal}) != 4 or len({p.parent for p in (active, candidate, backup, journal)}) != 1:
        raise OfflineActivationRejected('All transaction paths must be distinct siblings')
    if any(p.is_symlink() for p in (active, candidate, backup, journal)):
        raise OfflineActivationRejected('Symlink path rejected')
    if journal.exists() or backup.exists():
        raise OfflineActivationRejected('Previous activation artifacts require review')
    # Lifetime lock prevents even a manually started cooperating monitor.
    with offline_activation_lock(runtime_lock_path):
        stopped = verify_stopped()
        if stopped.get('launchagent_stopped') is not True:
            raise OfflineActivationRejected('LaunchAgent not verified stopped')
        require_safe_recovery(recovery_file)
        observed_binding = inspect_launch_plist(
            launch_plist, active_path=active, recovery_file=recovery_file,
            socket_path=socket_path)
        if observed_binding != binding:
            raise OfflineActivationRejected('Supplied binding does not match actual LaunchAgent')
        review = activation_preflight(active, candidate, observed_binding)
        if not review['changed_fields']:
            raise OfflineActivationRejected('No changes to activate')
        if not review['matches_active_monitor_checked_fields']:
            raise OfflineActivationRejected('Candidate requires LaunchAgent reconciliation; activation refused')
        old_hash, new_hash = review['active_sha256'], review['candidate_sha256']
        create_journal(journal, previous_sha256=old_hash, candidate_sha256=new_hash)
        try:
            result = activate_offline(active, candidate, backup,
                                      expected_active_sha256=old_hash,
                                      expected_candidate_sha256=new_hash,
                                      offline_authorization='OFFLINE_MONITOR_STOPPED')
            advance_journal(journal, expected_state='PREPARED', next_state='BACKUP_VERIFIED')
            advance_journal(journal, expected_state='BACKUP_VERIFIED', next_state='REPLACEMENT_WRITTEN')
            audit = audit_activation_state(active, candidate, backup,
                                           expected_previous_sha256=old_hash,
                                           expected_candidate_sha256=new_hash)
            if audit['state'] != 'REPLACEMENT_ON_DISK_REQUIRES_RUNTIME_RECONCILIATION':
                raise OfflineActivationRejected('Post-write audit failed; manual recovery required')
            advance_journal(journal, expected_state='REPLACEMENT_WRITTEN', next_state='VERIFIED')
        except BaseException:
            # Deliberately preserve journal and backup for forensic recovery.
            raise
    return {**result, 'journal_state': 'VERIFIED', 'runtime_restarted': False,
            'commissioning_authorized': False, 'arm_authorized': False,
            'manual_restart_required': True}
