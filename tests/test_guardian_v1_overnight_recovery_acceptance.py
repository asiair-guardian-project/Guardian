"""End-to-end, disk-backed overnight recovery acceptance; no network/hardware."""
from copy import deepcopy

import pytest

from modules.guardian_types import ProtectionTrigger, SafetyPowerResult, SessionState
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_incident_codec import encode_incident
from modules.guardian_v1_login_notice import notify_login, recovery_notice
from modules.guardian_v1_operator_commands import OperatorCommandHandler
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.protection_coordinator import initiate_protection


def clean_state():
    return dict(schema_version=2, active_incident=None,
                abort_acknowledged=False, incident_history=[],
                session_state='DISARMED', shutdown_clean=True,
                recovery_required=False)


def aborted_state():
    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda _action: SafetyPowerResult.FAILED,
    )
    state = clean_state()
    state.update(active_incident=encode_incident(incident),
                 session_state='ABORTED', shutdown_clean=False,
                 recovery_required=True)
    return state


def reboot(path):
    return GuardianV1Application(configured_capabilities=set(),
                                 recovery_store=GuardianV1RecoveryStore(path))


def test_unresolved_abort_survives_restart_and_notifies_once(tmp_path):
    path = tmp_path / 'recovery.json'
    state = aborted_state()
    GuardianV1RecoveryStore(path).write(state)
    app = reboot(path)
    assert app.supervisor.session_state is SessionState.ABORTED
    assert app.supervisor.recovery_blocked
    assert not app.supervisor.abort_acknowledged
    assert app.supervisor.incident is not None
    assert app.supervisor.export_recovery_state() == state
    notifications = []
    original = path.read_bytes()
    assert notify_login(path, notifier=lambda *args, **kwargs: notifications.append((args, kwargs)))
    assert len(notifications) == 1
    assert path.read_bytes() == original


def test_ack_is_durable_but_does_not_clear_abort_on_second_restart(tmp_path):
    path = tmp_path / 'recovery.json'
    state = aborted_state()
    GuardianV1RecoveryStore(path).write(state)
    app = reboot(path)
    handler = OperatorCommandHandler(app)
    token = handler.current_incident_token()
    result = handler.handle(dict(command='ACKNOWLEDGE_ABORT', incident_id=token,
                                 confirmed=True))
    assert result.ok, result
    saved = GuardianV1RecoveryStore(path).read()
    assert saved['abort_acknowledged'] is True
    assert saved['active_incident'] == state['active_incident']
    assert saved['session_state'] == 'ABORTED'
    assert saved['recovery_required'] is True
    again = reboot(path)
    assert again.supervisor.abort_acknowledged
    assert again.supervisor.recovery_blocked
    assert again.supervisor.session_state is SessionState.ABORTED
    assert again.supervisor.incident is not None
    assert recovery_notice(path) is not None
    assert GuardianV1RecoveryStore(path).read() == saved


def test_clean_restart_does_not_notify(tmp_path):
    path = tmp_path / 'recovery.json'
    GuardianV1RecoveryStore(path).write(clean_state())
    app = reboot(path)
    assert app.supervisor.incident is None
    called = []
    assert not notify_login(path, notifier=lambda *args, **kwargs: called.append(args))
    assert called == []


@pytest.mark.parametrize('kind', ['missing', 'corrupt'])
def test_missing_or_corrupt_state_fails_closed_and_notifies(tmp_path, kind):
    path = tmp_path / 'recovery.json'
    if kind == 'corrupt':
        path.write_text('{broken')
    app = reboot(path)
    assert app.supervisor.recovery_blocked
    assert app.supervisor.incident is None
    assert recovery_notice(path) is not None
    assert not path.exists() if kind == 'missing' else path.read_text() == '{broken'


def test_unconfirmed_ack_does_not_change_disk_or_supervisor(tmp_path):
    path = tmp_path / 'recovery.json'
    GuardianV1RecoveryStore(path).write(aborted_state())
    app = reboot(path)
    handler = OperatorCommandHandler(app)
    original = path.read_bytes()
    response = handler.handle(dict(command='ACKNOWLEDGE_ABORT',
                                   incident_id=handler.current_incident_token(),
                                   confirmed=False))
    assert not response.ok
    assert not app.supervisor.abort_acknowledged
    assert path.read_bytes() == original
