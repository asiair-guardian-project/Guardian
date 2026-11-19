import json
import socket
import threading

import pytest

from modules.guardian_v1_rehearsal_cli import live_monitor_is_armed, main
from tests.test_guardian_v1_rehearsal import FakeStrip

YAML = "config/config.example.yaml"


def go(argv, strip, tmp_path, answer="CUT", v06=False, socket_path=None):
    lines = []
    args = ["--installation-config", YAML, "--kasa-host", "192.168.1.30",
            "--evidence-dir", str(tmp_path / "ev"),
            "--operator-socket", str(socket_path or tmp_path / "none.sock")] + argv
    code = main(args, transport=strip, input_fn=lambda _p: answer,
                out=lines.append, v06_check=lambda _r: v06)
    return code, "\n".join(lines)


def test_without_confirm_token_nothing_is_switched(tmp_path):
    strip = FakeStrip()
    code, text = go([], strip, tmp_path)
    assert code == 2 and strip.commands == [] and "--confirm" in text


def test_wrong_typed_answer_nothing_is_switched(tmp_path):
    strip = FakeStrip()
    code, _ = go(["--confirm", "CUT_OUTLETS_2_3_4"], strip, tmp_path, answer="yes")
    assert code == 2 and strip.commands == []


def test_dry_run_switches_nothing(tmp_path):
    strip = FakeStrip()
    code, text = go(["--dry-run"], strip, tmp_path)
    assert code == 0 and strip.commands == [] and "DRY RUN" in text


def test_full_run_passes_and_writes_evidence(tmp_path):
    strip = FakeStrip()
    code, text = go(["--confirm", "CUT_OUTLETS_2_3_4"], strip, tmp_path)
    assert code == 0 and "PASS" in text and strip.on == {1}
    files = list((tmp_path / "ev").glob("rehearsal_*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["commissioning_authorized"] is False


def test_failure_returns_nonzero(tmp_path):
    code, text = go(["--confirm", "CUT_OUTLETS_2_3_4"], FakeStrip(cuts_outlet_1=True), tmp_path)
    assert code == 1 and "FAIL" in text


def test_refuses_when_v06_running(tmp_path):
    strip = FakeStrip()
    code, text = go(["--confirm", "CUT_OUTLETS_2_3_4"], strip, tmp_path, v06=True)
    assert code == 2 and strip.commands == [] and "v0.6" in text


def test_refuses_wrong_strip_address(tmp_path):
    lines = []
    code = main(["--installation-config", YAML, "--kasa-host", "10.0.0.9",
                 "--confirm", "CUT_OUTLETS_2_3_4"], transport=FakeStrip(),
                input_fn=lambda _p: "CUT", out=lines.append, v06_check=lambda _r: False)
    assert code == 2


def test_refuses_when_everything_already_off(tmp_path):
    strip = FakeStrip(on={1})
    code, _ = go(["--confirm", "CUT_OUTLETS_2_3_4"], strip, tmp_path)
    assert code == 2 and strip.commands == []


def _serve(path, reply):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(path)); srv.listen(1)

    def once():
        c, _ = srv.accept(); c.recv(100); c.sendall(reply); c.close(); srv.close()
    t = threading.Thread(target=once, daemon=True); t.start()
    return t


@pytest.mark.parametrize("reply,refuse", [
    (b'{"ok": true, "armed": true}\n', True),
    (b'{"ok": true, "state": {"hardware_execution_enabled": true}}\n', True),
    (b'{"ok": true, "armed": false, "hardware_execution_enabled": false}\n', False),
    (b'garbage\n', True),
])
def test_live_monitor_status_check(reply, refuse):
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp(prefix="gr", dir="/tmp"))
    p = d / "s.sock"
    t = _serve(p, reply)
    assert (live_monitor_is_armed(p) is not None) is refuse
    t.join(2)


def test_missing_socket_is_fine(tmp_path):
    assert live_monitor_is_armed(tmp_path / "nope.sock") is None
