import json
import os
import shutil
import socket
import tempfile
import threading

import pytest

import main as v06_main
from modules.guardian_v1_start_guard import v1_blocks_start


class FakeMonitor:
    """Tiny stand-in for the v1.0 operator socket."""

    def __init__(self, reply_bytes, hang=False):
        self.dir = tempfile.mkdtemp(dir="/tmp")
        self.path = os.path.join(self.dir, "op.sock")
        self.reply_bytes = reply_bytes
        self.hang = hang
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(1)
        self.server.settimeout(5)
        self.requests = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(3)
            try:
                self.requests.append(conn.recv(4096))
                if self.hang:
                    threading.Event().wait(3)
                else:
                    conn.sendall(self.reply_bytes)
            except OSError:
                pass

    def close(self):
        self.server.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def status(**fields):
    reply = {"ok": True, "code": "STATUS"}
    reply.update(fields)
    return json.dumps(reply).encode() + b"\n"


@pytest.fixture
def monitor():
    made = []

    def make(reply_bytes, hang=False):
        m = FakeMonitor(reply_bytes, hang)
        made.append(m)
        return m

    yield make
    for m in made:
        m.close()


def test_armed_with_hardware_blocks_v06(monitor):
    m = monitor(status(armed=True, hardware_execution_enabled=True))
    reason = v1_blocks_start(m.path)
    assert reason and "ARMED" in reason
    assert json.loads(m.requests[0]) == {"command": "STATUS"}


@pytest.mark.parametrize("armed,hardware", [(True, False), (False, True), (False, False)])
def test_anything_less_than_armed_with_hardware_lets_v06_start(monitor, armed, hardware):
    m = monitor(status(armed=armed, hardware_execution_enabled=hardware))
    assert v1_blocks_start(m.path) is None


@pytest.mark.parametrize("reply", [
    b"not json\n",
    b"[1, 2]\n",
    b'{"code": "ERROR", "armed": true, "hardware_execution_enabled": true}\n',
    b'{"code": "STATUS", "armed": "yes", "hardware_execution_enabled": "yes"}\n',
    b"no newline at all",
    b"",
])
def test_unclear_answers_fail_open(monitor, reply):
    m = monitor(reply)
    assert v1_blocks_start(m.path) is None


def test_missing_socket_fails_open(tmp_path):
    assert v1_blocks_start(str(tmp_path / "nothing.sock")) is None


def test_a_monitor_that_never_answers_fails_open_quickly(monitor):
    import time
    m = monitor(b"", hang=True)
    started = time.monotonic()
    assert v1_blocks_start(m.path, timeout=0.3) is None
    assert time.monotonic() - started < 2


def test_v06_main_exits_without_starting_when_blocked(monkeypatch, capsys):
    started = []
    monkeypatch.setattr(v06_main, "_v1_start_block_reason", lambda: "v1 armed")
    monkeypatch.setattr(v06_main, "Guardian", lambda *a, **k: started.append("guardian"))
    monkeypatch.setattr(v06_main, "parse_args", lambda: type("A", (), {"armed": False})())
    with pytest.raises(SystemExit) as exit_info:
        v06_main.main()
    assert exit_info.value.code == 75
    assert started == []
    assert "v1 armed" in capsys.readouterr().out


def test_v06_main_starts_normally_when_not_blocked(monkeypatch):
    calls = []

    class FakeGuardian:
        def restore_emergency_state(self):
            calls.append("restore")

    class FakeLoop:
        def __init__(self, guardian):
            calls.append("loop")

        def run(self):
            calls.append("run")

    monkeypatch.setattr(v06_main, "_v1_start_block_reason", lambda: None)
    monkeypatch.setattr(v06_main, "Guardian", FakeGuardian)
    monkeypatch.setattr(v06_main, "MonitorLoop", FakeLoop)
    monkeypatch.setattr(v06_main, "parse_args", lambda: type("A", (), {"armed": False})())
    v06_main.main()
    assert calls == ["restore", "loop", "run"]


def test_a_broken_guard_never_stops_v06(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def broken(name, *args, **kwargs):
        if name == "modules.guardian_v1_start_guard":
            raise RuntimeError("guard module is broken")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    assert v06_main._v1_start_block_reason() is None
