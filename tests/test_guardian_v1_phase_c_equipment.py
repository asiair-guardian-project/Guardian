from types import SimpleNamespace
from modules.guardian_v1_operator_socket import operator_status


def test_status_can_include_readonly_equipment_snapshot():
    sup = SimpleNamespace(incident=None, recovery_blocked=False, session_state=SimpleNamespace(name="DISARMED"), recovery_block_reason=None, abort_acknowledged=False)
    app = SimpleNamespace(supervisor=sup, recovery_store=None, mode=SimpleNamespace(hardware_execution_enabled=False, monitor_only=True))
    handler = SimpleNamespace(current_incident_token=lambda: None)
    snapshot = {"roof": "CLOSED", "controller": "ONLINE", "mount_motion": "UNKNOWN", "observed_at_utc": "2026-11-01T00:00:00+00:00"}
    status = operator_status(app, handler, observation_provider=lambda: snapshot)
    assert status["equipment"] == snapshot
    assert not status["hardware_execution_enabled"]
    assert not status["arm_available"]


def test_no_observation_does_not_fabricate_equipment_state():
    sup = SimpleNamespace(incident=None, recovery_blocked=False, session_state=SimpleNamespace(name="DISARMED"), recovery_block_reason=None, abort_acknowledged=False)
    app = SimpleNamespace(supervisor=sup, recovery_store=None, mode=SimpleNamespace(hardware_execution_enabled=False, monitor_only=True))
    handler = SimpleNamespace(current_incident_token=lambda: None)
    status = operator_status(app, handler, observation_provider=lambda: None)
    assert "equipment" not in status
