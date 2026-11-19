import socket
import threading

from modules.capability_model import installation_ready
from modules.guardian_types import Capability, CapabilityStatus
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_socket import GuardianOperatorSocket


def test_missing_commissioning_fails_closed():
    statuses = {cap: CapabilityStatus.AVAILABLE for cap in Capability}
    assert installation_ready(None, "fingerprint", statuses) is False


def test_disconnected_client_does_not_crash_operator_socket(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "operator.sock"
    app = GuardianV1Application(configured_capabilities=set())
    server = GuardianOperatorSocket(app, path)
    server.start()
    try:
        # Force sendall to simulate a GUI that disconnected before response.
        # This also checks that a subsequent valid request still succeeds.
        original = socket.socket.sendall
        # socket.socket methods cannot safely be monkeypatched globally; use
        # a real disconnect with RST via SO_LINGER.
        import struct
        def client_disconnect():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.connect(str(path))
                conn.sendall(b'{"command":"STATUS"}\n')
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        t = threading.Thread(target=server.serve_once)
        t.start()
        client_disconnect()
        t.join(timeout=3)
        assert not t.is_alive()
        t = threading.Thread(target=server.serve_once)
        t.start()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.connect(str(path))
            conn.sendall(b'{"command":"STATUS"}\n')
            assert b'"STATUS"' in conn.recv(4096)
        t.join(timeout=3)
        assert not t.is_alive()
    finally:
        server.close()
