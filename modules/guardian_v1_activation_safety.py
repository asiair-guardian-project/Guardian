"""Read-only Phase C maintenance safety gates.

These checks do not stop or restart a monitor and cannot authorize activation.
"""
from __future__ import annotations

from pathlib import Path
import os
import plistlib
import stat

from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_setup_binding import MonitorBinding


class MaintenanceSafetyError(RuntimeError):
    pass


def require_safe_recovery(recovery_file):
    """Fail closed on missing/corrupt state, incident, recovery, or non-disarmed session."""
    path = Path(recovery_file).expanduser().absolute()
    if path.is_symlink():
        raise MaintenanceSafetyError('Recovery file is a symlink')
    try:
        state = GuardianV1RecoveryStore(path).read()
    except Exception as exc:
        raise MaintenanceSafetyError('Recovery state cannot be verified') from exc
    if (state['session_state'] != 'DISARMED' or
            state['active_incident'] is not None or
            state['recovery_required'] or
            not state['shutdown_clean']):
        raise MaintenanceSafetyError('Session or recovery state blocks maintenance')
    return {'safe_disarmed': True, 'incident_free': True, 'hardware_commands': 0}


def inspect_launch_plist(plist_path, *, active_path, recovery_file, socket_path,
                         expected_label='org.guardian.v1.monitor'):
    """Validate LaunchAgent provenance and derive its authoritative binding.

    Does not rewrite, load, unload or kickstart the LaunchAgent.
    """
    path = Path(plist_path).expanduser().absolute()
    if path.is_symlink():
        raise MaintenanceSafetyError('LaunchAgent plist is a symlink')
    try:
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
            raise MaintenanceSafetyError('LaunchAgent plist ownership or permissions unsafe')
        with path.open('rb') as stream:
            doc = plistlib.load(stream)
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException) as exc:
        raise MaintenanceSafetyError('LaunchAgent plist cannot be read') from exc
    if not isinstance(doc, dict) or doc.get('Label') != expected_label:
        raise MaintenanceSafetyError('Unexpected LaunchAgent identity')
    args = doc.get('ProgramArguments')
    if not isinstance(args, list) or not args or any(not isinstance(a, str) for a in args):
        raise MaintenanceSafetyError('Invalid LaunchAgent arguments')
    if '--continuous-monitor' not in args:
        raise MaintenanceSafetyError('Not a continuous monitor LaunchAgent')
    def required(flag):
        if args.count(flag) != 1:
            raise MaintenanceSafetyError('Missing or duplicate LaunchAgent option')
        pos = args.index(flag)
        if pos + 1 >= len(args) or args[pos + 1].startswith('--'):
            raise MaintenanceSafetyError('Missing LaunchAgent option value')
        return args[pos + 1]
    try:
        actual_paths = {
            '--installation-config': active_path,
            '--recovery-file': recovery_file,
            '--operator-socket': socket_path,
        }
        for flag, expected in actual_paths.items():
            if Path(required(flag)).expanduser().absolute() != Path(expected).expanduser().absolute():
                raise MaintenanceSafetyError('LaunchAgent path does not match installation')
        binding = MonitorBinding(
            asiair_host=required('--asiair-host'),
            alpaca_host=required('--alpaca-host'),
            alpaca_port=int(required('--alpaca-port')),
            alpaca_device=int(required('--alpaca-device')),
            cycle_seconds=float(required('--cycle-seconds')),
        )
        if not 1 <= binding.alpaca_port <= 65535 or binding.cycle_seconds <= 0:
            raise MaintenanceSafetyError('Invalid LaunchAgent binding')
    except (TypeError, ValueError, OverflowError) as exc:
        raise MaintenanceSafetyError('Invalid LaunchAgent numeric binding') from exc
    return binding
