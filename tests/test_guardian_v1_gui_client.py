import json
import socket
import threading
import pytest
from guardian_v1_gui import send_operator_request


def test_gui_client_uses_existing_operator_protocol(tmp_path):
    path = tmp_path / 'op.sock'
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    seen = []
    def serve():
        conn, _ = server.accept()
        with conn:
            seen.append(json.loads(conn.recv(4096).split(b'\n')[0]))
            conn.sendall(b'{"ok":true,"code":"STATUS","armed":false}\n')
    worker = threading.Thread(target=serve)
    worker.start()
    try:
        assert send_operator_request(path, {'command': 'STATUS'})['code'] == 'STATUS'
        assert seen == [{'command': 'STATUS'}]
    finally:
        worker.join(timeout=3)
        server.close()


def test_gui_client_refuses_absent_socket(tmp_path):
    with pytest.raises(ConnectionError):
        send_operator_request(tmp_path / 'absent.sock', {'command': 'STATUS'})
