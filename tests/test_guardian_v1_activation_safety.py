import plistlib
import pytest
from modules.guardian_v1_activation_safety import (
    require_safe_recovery, inspect_launch_plist, MaintenanceSafetyError)


def test_missing_recovery_fails_closed(tmp_path):
    with pytest.raises(MaintenanceSafetyError, match='cannot be verified'):
        require_safe_recovery(tmp_path/'missing.json')


def test_recovery_symlink_fails_closed(tmp_path):
    target = tmp_path/'target'
    target.write_text('{}')
    (tmp_path/'link').symlink_to(target)
    with pytest.raises(MaintenanceSafetyError, match='symlink'):
        require_safe_recovery(tmp_path/'link')


def make_plist(tmp_path, args=None):
    args = args or ['python', 'guardian_v1.py', '--continuous-monitor',
        '--installation-config', str(tmp_path/'config.yaml'),
        '--recovery-file', str(tmp_path/'recovery.json'),
        '--operator-socket', str(tmp_path/'operator.sock'),
        '--asiair-host', 'example.org', '--alpaca-host', 'roof.example.org',
        '--alpaca-port', '11111', '--alpaca-device', '17', '--cycle-seconds', '5']
    path = tmp_path/'monitor.plist'
    path.write_bytes(plistlib.dumps({'Label':'org.guardian.v1.monitor', 'ProgramArguments': args}))
    return path


def inspect(tmp_path, path):
    return inspect_launch_plist(path, active_path=tmp_path/'config.yaml',
        recovery_file=tmp_path/'recovery.json', socket_path=tmp_path/'operator.sock')


def test_launch_binding_derived_from_actual_plist(tmp_path):
    b = inspect(tmp_path, make_plist(tmp_path))
    assert (b.asiair_host, b.alpaca_port, b.cycle_seconds) == ('example.org', 11111, 5.0)


def test_plist_wrong_config_path_rejected(tmp_path):
    p = make_plist(tmp_path)
    data = plistlib.loads(p.read_bytes())
    args = data['ProgramArguments']
    args[args.index('--installation-config')+1] = '/tmp/wrong.yaml'
    p.write_bytes(plistlib.dumps(data))
    with pytest.raises(MaintenanceSafetyError, match='does not match'):
        inspect(tmp_path, p)


def test_plist_duplicate_flag_rejected(tmp_path):
    p = make_plist(tmp_path)
    data = plistlib.loads(p.read_bytes())
    data['ProgramArguments'].extend(['--asiair-host', 'different'])
    p.write_bytes(plistlib.dumps(data))
    with pytest.raises(MaintenanceSafetyError, match='duplicate'):
        inspect(tmp_path, p)


def test_plist_symlink_rejected(tmp_path):
    p = make_plist(tmp_path)
    (tmp_path/'link').symlink_to(p)
    with pytest.raises(MaintenanceSafetyError, match='symlink'):
        inspect(tmp_path, tmp_path/'link')


def test_plist_untrusted_label_rejected(tmp_path):
    p = make_plist(tmp_path)
    data = plistlib.loads(p.read_bytes()); data['Label'] = 'other'
    p.write_bytes(plistlib.dumps(data))
    with pytest.raises(MaintenanceSafetyError, match='identity'):
        inspect(tmp_path, p)


def test_plist_world_writable_rejected(tmp_path):
    p = make_plist(tmp_path); p.chmod(0o666)
    with pytest.raises(MaintenanceSafetyError, match='permissions'):
        inspect(tmp_path, p)
