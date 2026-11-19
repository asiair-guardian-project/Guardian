from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_socket import GuardianOperatorSocket, operator_status

def test_monitor_only_status_disallows_arm(tmp_path):
    app = GuardianV1Application(configured_capabilities=set())
    socket = GuardianOperatorSocket(app, tmp_path / "unused.sock")
    status = operator_status(app, socket.handler, socket.gate)
    assert status["arm_available"] is False
    assert status["hardware_execution_enabled"] is False
    assert status["armed"] is False
