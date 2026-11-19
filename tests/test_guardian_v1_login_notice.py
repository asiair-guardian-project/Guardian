"""Login notification must never change recovery state or authorize imaging."""
from modules.guardian_v1_login_notice import recovery_notice, notify_login
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore


def state(*, recovery_required=False, shutdown_clean=True):
    return dict(schema_version=2, active_incident=None, abort_acknowledged=False,
                incident_history=[], session_state='DISARMED',
                shutdown_clean=shutdown_clean, recovery_required=recovery_required)


def test_missing_file_requires_operator_notice(tmp_path):
    assert 'unavailable' in recovery_notice(tmp_path / 'missing.json')


def test_corrupt_file_requires_operator_notice(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text('{invalid')
    assert 'invalid' in recovery_notice(path)


def test_clean_recovery_sends_no_notice(tmp_path):
    path = tmp_path / 'state.json'
    GuardianV1RecoveryStore(path).write(state())
    called = []
    assert not notify_login(path, notifier=lambda *a, **k: called.append((a,k)))
    assert not called


def test_latched_recovery_notifies_once_and_never_writes(tmp_path):
    path = tmp_path / 'state.json'
    GuardianV1RecoveryStore(path).write(state(recovery_required=True, shutdown_clean=False))
    before = path.read_bytes()
    calls = []
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
    assert notify_login(path, notifier=fake_run)
    assert len(calls) == 1
    assert calls[0][0][0] == 'osascript'
    assert path.read_bytes() == before


def test_unclean_shutdown_notifies(tmp_path):
    path = tmp_path / 'state.json'
    GuardianV1RecoveryStore(path).write(state(shutdown_clean=False))
    assert 'inspection' in recovery_notice(path)
