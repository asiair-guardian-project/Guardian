"""Read-only login alert for an unresolved Guardian v1 recovery incident.

This is intended to be invoked once per interactive login by a LaunchAgent.
It never writes recovery state, opens hardware adapters, or acknowledges an abort.
"""
import argparse
import subprocess
from pathlib import Path

from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore, RecoveryStateError


NOTICE_SCRIPT = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv) subtitle "ARM BLOCKED"
end run'''


def recovery_notice(recovery_path):
    """Return notification message or None for a verified clean state.

    Fail closed for missing or corrupt recovery state: operator must be told.
    """
    try:
        state = GuardianV1RecoveryStore(recovery_path).read()
    except (RecoveryStateError, OSError, ValueError):
        return "Recovery state unavailable or invalid. Inspect Guardian before imaging."
    if state['active_incident'] is not None:
        return "Unresolved safety incident. Inspect Guardian recovery before imaging."
    if state['recovery_required'] or not state['shutdown_clean']:
        return "Guardian recovery requires operator inspection before imaging."
    return None


def notify_login(recovery_path, *, notifier=None):
    """Notify at most once per invocation. Returns True if notice requested."""
    message = recovery_notice(recovery_path)
    if message is None:
        return False
    run = notifier or subprocess.run
    run(['osascript', '-e', NOTICE_SCRIPT, 'Guardian — Recovery Required', message],
        check=True, capture_output=True, text=True, timeout=10)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description='Guardian v1 read-only login recovery notice')
    parser.add_argument('--recovery-file', type=Path, required=True)
    args = parser.parse_args(argv)
    notify_login(args.recovery_file)


if __name__ == '__main__':
    main()
