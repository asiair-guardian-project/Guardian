"""The read-only local web page: what it serves, and what it refuses."""
import http.client
import json
import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from modules.guardian_v1_web import (
    STATUS_FIELDS, ask_monitor, make_server, monitor_status, tail_lines)

STATUS_REPLY = {
    "ok": True, "code": "STATUS", "session": "DISARMED", "armed": False,
    "arm_available": False, "arm_unavailable_reason": "monitor-only",
    "hardware_execution_enabled": False, "recovery_reason": None,
    "arm_blocked": False, "incident_active": False, "acknowledged": False,
    "unresolved_actions": [],
    "equipment": {"roof": "CLOSED", "controller": "ONLINE", "mount_motion": "UNKNOWN",
                  "observed_at_utc": "2026-11-09T18:00:00+00:00"},
    # These must never reach the browser:
    "incident_id": "a" * 64, "recovery_file": "/Users/x/recovery.json",
    "setup": {"secret": "endpoint"},
}


class FakeMonitor:
    """A tiny stand-in for the monitor's operator socket."""

    def __init__(self, path, reply=None, stall=False):
        self.path, self.reply, self.stall = path, reply, stall
        self.requests = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen(8)
        self.server.settimeout(0.2)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        held = []
        while not self.stop.is_set():
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            data = b""
            conn.settimeout(1)
            try:
                while b"\n" not in data:
                    part = conn.recv(1024)
                    if not part:
                        break
                    data += part
            except OSError:
                pass
            self.requests.append(data)
            if self.stall:
                held.append(conn)  # never answer
                continue
            conn.sendall(json.dumps(self.reply).encode() + b"\n")
            conn.close()

    def close(self):
        self.stop.set()
        self.thread.join(2)
        self.server.close()


@pytest.fixture
def workdir():
    directory = Path(tempfile.mkdtemp(prefix="gw", dir="/tmp"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def web(workdir):
    monitor = FakeMonitor(workdir / "m.sock", STATUS_REPLY)
    logs = workdir / "logs"
    logs.mkdir()
    (logs / "guardian_v1.log").write_text(
        "2026-11-09 12:00:00 [INFO    ] ROOF | OPEN | Roof status changed to OPEN.\n")
    server = make_server(workdir / "m.sock", logs, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def get(path, host=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host if host is not None else f"127.0.0.1:{port}")
        conn.endheaders()
        response = conn.getresponse()
        body = response.read()
        headers = dict(response.getheaders())
        conn.close()
        return response.status, body, headers

    yield type("W", (), {"get": staticmethod(get), "port": port, "monitor": monitor,
                         "server": server, "logs": logs})
    server.shutdown()
    server.server_close()
    monitor.close()


def test_status_passes_only_the_allowed_fields(web):
    code, body, _ = web.get("/api/status")
    data = json.loads(body)
    assert code == 200 and data["connected"] is True
    assert set(data) <= set(STATUS_FIELDS) | {"connected"}
    for leaked in ("incident_id", "recovery_file", "setup"):
        assert leaked not in data
    assert data["equipment"]["roof"] == "CLOSED"


def test_only_status_is_ever_asked_of_the_monitor(web):
    for path in ("/", "/api/status", "/api/events", "/api/nights", "/app.js"):
        web.get(path)
    assert web.monitor.requests
    assert all(json.loads(r) == {"command": "STATUS"} for r in web.monitor.requests)


def test_no_contact_is_reported_as_not_connected(workdir):
    assert monitor_status(workdir / "missing.sock") == {"connected": False}


def test_a_monitor_that_never_answers_gives_no_contact_quickly(workdir):
    monitor = FakeMonitor(workdir / "s.sock", stall=True)
    try:
        started = time.monotonic()
        assert ask_monitor(workdir / "s.sock", {"command": "STATUS"}, timeout=0.5) is None
        assert time.monotonic() - started < 2
    finally:
        monitor.close()


def test_a_garbled_or_wrong_reply_is_no_contact(workdir):
    monitor = FakeMonitor(workdir / "g.sock", {"ok": False, "code": "INVALID_REQUEST"})
    try:
        assert monitor_status(workdir / "g.sock") == {"connected": False}
    finally:
        monitor.close()


def test_a_foreign_host_header_is_refused(web):
    for host in ("evil.example", "evil.example:%d" % web.port, "127.0.0.1",
                 "127.0.0.1:1", "localhost.evil.example:%d" % web.port, ""):
        assert web.get("/api/status", host=host)[0] == 403, host
    assert web.get("/api/status", host=f"localhost:{web.port}")[0] == 200


def test_only_get_is_allowed(web):
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert web.get("/api/status", method=method)[0] == 405


def test_the_server_listens_on_loopback_only(web):
    assert web.server.server_address[0] == "127.0.0.1"
    import inspect
    assert "host" not in inspect.signature(make_server).parameters


def test_security_headers_and_no_cors(web):
    for path in ("/", "/api/status", "/app.js"):
        _, _, headers = web.get(path)
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "script-src 'self'" in headers["Content-Security-Policy"]
        assert not any(h.lower().startswith("access-control") for h in headers)


def test_unknown_paths_and_traversal_are_404(web):
    for path in ("/nope", "/../config.yaml", "/app.js/../../config.yaml",
                 "/%2e%2e/config.yaml", "/api"):
        assert web.get(path)[0] == 404


def test_the_page_and_its_files_are_served(web):
    code, body, headers = web.get("/")
    assert code == 200 and b"Guardian 1.0" in body and "text/html" in headers["Content-Type"]
    assert web.get("/app.js")[0] == 200 and web.get("/app.css")[0] == 200


def test_events_endpoint_returns_the_log_tail(web):
    data = json.loads(web.get("/api/events")[1])
    assert data["lines"] == [
        "2026-11-09 12:00:00 [INFO    ] ROOF | OPEN | Roof status changed to OPEN."]


def test_tail_lines_limits_and_tolerates_a_missing_file(workdir):
    assert tail_lines(workdir / "none.log") == []
    path = workdir / "big.log"
    path.write_text("".join(f"line {i}\n" for i in range(500)))
    out = tail_lines(path, 40)
    assert len(out) == 40 and out[-1] == "line 499"


def test_nights_endpoint_summarizes_the_log(web):
    (web.logs / "guardian_v1.log").write_text(
        "2026-11-04 01:09:43 [INFO    ] ROOF | CLOSED | x\n"
        "2026-11-04 01:11:46 [INFO    ] ROOF | OPEN | x\n")
    text = json.loads(web.get("/api/nights")[1])["text"]
    assert "closed 01:09:43 - reopened 01:11:46  (2 min)" in text


def test_the_page_never_treats_monitor_text_as_html():
    root = Path(__file__).resolve().parent.parent / "web"
    js = (root / "app.js").read_text()
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js
    assert "NO CONTACT WITH THE MONITOR" in js
    assert "<script>" not in (root / "index.html").read_text()  # no inline script


def test_the_page_has_no_buttons_or_forms():
    html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text()
    assert "<button" not in html and "<form" not in html and "<input" not in html


def test_events_reach_back_into_the_archive_after_midnight(workdir):
    logs = workdir / "logs"
    logs.mkdir()
    (logs / "guardian_v1.log.2026-11-06").write_text(
        "".join(f"old {i}\n" for i in range(10)))
    (logs / "guardian_v1.log").write_text("new 0\nnew 1\n")
    out = tail_lines(logs / "guardian_v1.log", 5)
    assert out == ["old 7", "old 8", "old 9", "new 0", "new 1"]
    assert tail_lines(logs / "guardian_v1.log", 2) == ["new 0", "new 1"]


def test_mount_motion_is_not_shown_because_v10_does_not_track_it():
    root = Path(__file__).resolve().parent.parent
    for name in ("web/index.html", "web/app.js", "GuardianApp.swift"):
        text = (root / name).read_text().lower()
        assert "mount motion" not in text and "mount_motion" not in text, name


# --- Tailscale access ----------------------------------------------------------

from modules.guardian_v1_web import (  # noqa: E402
    _serve, make_tailscale_server, validate_host_names, validate_tailscale_address)


def test_only_tailscale_addresses_are_accepted():
    for good in ("100.64.0.1", "100.101.102.103", "100.127.255.254", " 100.100.1.1 "):
        assert validate_tailscale_address(good) == good.strip()
    for bad in ("0.0.0.0", "127.0.0.1", "192.168.1.5", "10.0.0.1", "192.168.1.30",
                "8.8.8.8", "100.63.255.255", "100.128.0.1", "::1", "fd7a:115c:a1e0::1",
                "marks-mini", "", "100.64.0.1/10", "100.64.0.1:8765", None):
        with pytest.raises(ValueError):
            validate_tailscale_address(bad)


def test_the_public_tailscale_server_refuses_every_other_address(workdir):
    for bad in ("0.0.0.0", "127.0.0.1", "192.168.1.5", "192.168.1.30"):
        with pytest.raises(ValueError):
            make_tailscale_server(workdir / "m.sock", workdir, bad, port=0)


def test_host_names_must_be_plain():
    assert validate_host_names(["Marks-Mini", "mini.tail1234.ts.net"]) == [
        "marks-mini", "mini.tail1234.ts.net"]
    for bad in ("evil.example:80", "a/b", "a b", "", "-x", "x-", "a@b", "http://x"):
        with pytest.raises(ValueError):
            validate_host_names([bad])


def _get(port, path, host):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", host)
    conn.endheaders()
    response = conn.getresponse()
    response.read()
    conn.close()
    return response.status


def test_a_tailscale_style_server_answers_only_to_its_own_names(workdir):
    # The real server binds a 100.x address, which this machine does not have,
    # so the same code is exercised on loopback with the Tailscale name list.
    server = _serve("127.0.0.1", 0, workdir / "m.sock", workdir,
                    ["100.101.102.103", "marks-mini"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        assert _get(port, "/api/status", f"100.101.102.103:{port}") == 200
        assert _get(port, "/api/status", f"marks-mini:{port}") == 200
        assert _get(port, "/api/status", f"MARKS-MINI:{port}") == 200
        for bad in (f"127.0.0.1:{port}", f"localhost:{port}", "marks-mini",
                    f"marks-mini:{port + 1}", f"evil.example:{port}", ""):
            assert _get(port, "/api/status", bad) == 403, bad
    finally:
        server.shutdown()
        server.server_close()


def test_the_loopback_server_does_not_answer_to_tailscale_names(web):
    assert web.get("/api/status", host=f"marks-mini:{web.port}")[0] == 403
    assert web.get("/api/status", host=f"100.101.102.103:{web.port}")[0] == 403


def test_the_server_never_does_a_reverse_name_lookup(workdir, monkeypatch):
    import socket as socket_module

    def refuse(*args, **kwargs):
        raise AssertionError("getfqdn must not be called")
    monkeypatch.setattr(socket_module, "getfqdn", refuse)
    server = make_server(workdir / "m.sock", workdir, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def _cli():
    import importlib
    return importlib.import_module("guardian_v1_web")


def _args(cli, workdir, *extra):
    return cli.parse_args(["--operator-socket", str(workdir / "m.sock"),
                           "--log-dir", str(workdir), "--port", "0", *extra])


def test_an_invalid_tailscale_address_falls_back_to_loopback(workdir):
    cli, said = _cli(), []
    servers = cli.start_servers(_args(cli, workdir, "--tailscale-address", "192.168.1.5"),
                                say=said.append)
    try:
        assert len(servers) == 1 and servers[0].server_address[0] == "127.0.0.1"
        text = "\n".join(said)
        assert "NOT listening on Tailscale" in text
        assert "Continuing on 127.0.0.1 only" in text
        assert said[-1] == "(Ctrl-C to stop)"
    finally:
        for server in servers:
            server.server_close()


def test_a_valid_address_that_cannot_be_bound_also_falls_back(workdir, monkeypatch):
    cli, said = _cli(), []

    def cannot_bind(*args, **kwargs):
        raise OSError(49, "Can't assign requested address")
    monkeypatch.setattr(cli, "make_tailscale_server", cannot_bind)
    servers = cli.start_servers(_args(cli, workdir, "--tailscale-address", "100.100.1.2"),
                                say=said.append)
    try:
        assert len(servers) == 1
        assert "NOT listening on Tailscale: [Errno 49]" in "\n".join(said)
    finally:
        servers[0].server_close()


def test_a_usable_tailscale_address_adds_a_second_server_and_prints_both_urls(workdir, monkeypatch):
    cli, said = _cli(), []
    # This machine has no 100.x address, so a loopback server stands in for it.
    monkeypatch.setattr(cli, "make_tailscale_server",
                        lambda sock, logs, address, port, names: _serve(
                            "127.0.0.1", 0, sock, logs, [address, *names]))
    servers = cli.start_servers(
        _args(cli, workdir, "--tailscale-address", "100.100.1.2",
              "--allow-host", "marks-mini"), say=said.append)
    try:
        assert len(servers) == 2
        text = "\n".join(said)
        assert "and over Tailscale:      http://100.100.1.2:" in text
        assert "http://marks-mini:" in text
        assert "NOT listening" not in text
    finally:
        for server in servers:
            server.server_close()


def test_startup_messages_are_flushed_when_printed(monkeypatch):
    cli, calls = _cli(), []
    monkeypatch.setattr("builtins.print", lambda *a, **k: calls.append(k))
    cli.say("hello")
    assert calls == [{"flush": True}]
