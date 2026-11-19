import json
import socket
import threading
from modules.guardian_v1_operator_socket import GuardianOperatorSocket

class Gate:
    def __init__(self, app):
        self.application = app
        self.armed = False
        self.allow = False
    def arm(self):
        if not self.allow: return False
        self.armed = True
        return True
    def disarm(self): self.armed = False

class Supervisor:
    incident = None
    recovery_blocked = False
    recovery_block_reason = None
    abort_acknowledged = False
    class Session:
        name = "DISARMED"
    session_state = Session()

class App:
    supervisor = Supervisor()
    recovery_store = None

def test_arm_disarm_and_reject_malformed_requests(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "op.sock"
    app = App()
    gate = Gate(app)
    service = GuardianOperatorSocket(app, path, gate=gate)
    service.start()
    def send(payload):
        worker = threading.Thread(target=service.serve_once)
        worker.start()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(path))
            client.sendall(json.dumps(payload).encode() + b"\n")
            reply = json.loads(client.recv(4096))
        worker.join(timeout=3)
        assert not worker.is_alive()
        return reply
    try:
        assert send({"command":"STATUS"})["armed"] is False
        assert send({"command":"ARM", "confirmed":False})["ok"] is False
        assert send({"command":"ARM", "confirmed":True})["code"] == "ARM_BLOCKED"
        gate.allow = True
        assert send({"command":"ARM", "confirmed":True})["code"] == "ARMED"
        assert send({"command":"STATUS"})["armed"] is True
        assert send({"command":"DISARM", "confirmed":True, "extra":1})["ok"] is False
        assert send({"command":"DISARM", "confirmed":True})["code"] == "DISARMED"
        assert send({"command":"STATUS"})["armed"] is False
    finally:
        service.close()

def test_default_socket_has_no_arm_authority(tmp_path):
    directory=tmp_path / "private"
    directory.mkdir(mode=0o700)
    service=GuardianOperatorSocket(App(), directory / "op.sock")
    assert service._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "UNSUPPORTED"
