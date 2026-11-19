import json
import socket
import threading

from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_socket import GuardianOperatorSocket
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_types import ProtectionTrigger, SafetyPowerResult, SessionState
from modules.protection_coordinator import initiate_protection


def send(path, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.connect(str(path))
        conn.sendall(json.dumps(request).encode() + b'\n')
        return json.loads(conn.recv(8192))


def test_socket_ack_is_durable_and_incident_stays_latched(tmp_path):
    state_path = tmp_path / 'state.json'
    app = GuardianV1Application(configured_capabilities=set())
    app.supervisor._incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda _: SafetyPowerResult.FAILED,
    )
    app.supervisor._session_state = SessionState.ABORTED
    app.recovery_store = GuardianV1RecoveryStore(state_path)
    app.recovery_store.write(app.supervisor.export_recovery_state())
    socket_dir = tmp_path / 'private'
    socket_dir.mkdir(mode=0o700)
    path = socket_dir / 'operator.sock'
    service = GuardianOperatorSocket(app, path)
    service.start()
    try:
        def request(data):
            thread = threading.Thread(target=service.serve_once)
            thread.start()
            result = send(path, data)
            thread.join(timeout=2)
            assert not thread.is_alive()
            return result
        status = request({'command': 'STATUS'})
        assert status['arm_blocked'] is True
        token = status['incident_id']
        assert len(token) == 64
        assert len(status['unresolved_actions']) == 3
        assert request({'command': 'ACKNOWLEDGE_ABORT', 'incident_id': token, 'confirmed': False})['ok'] is False
        assert request({'command': 'ACKNOWLEDGE_ABORT', 'incident_id': '0'*64, 'confirmed': True})['ok'] is False
        assert request({'command': 'ARM', 'incident_id': token, 'confirmed': True})['ok'] is False
        assert request({'command': 'ACKNOWLEDGE_ABORT', 'incident_id': token, 'confirmed': True})['ok'] is True
        assert app.supervisor.incident is not None
        assert len(app.supervisor.incident.unresolved_actions) == 3
        assert request({'command': 'STATUS'})['arm_blocked'] is True
        restored = GuardianV1Application(configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(state_path))
        assert restored.supervisor.abort_acknowledged is True
        assert restored.supervisor.incident is not None
    finally:
        service.close()
    assert not path.exists()


def test_socket_rejects_insecure_directory(tmp_path):
    directory = tmp_path / 'world'
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)
    app = GuardianV1Application(configured_capabilities=set())
    service = GuardianOperatorSocket(app, directory / 'socket')
    import pytest
    with pytest.raises(PermissionError):
        service.start()
