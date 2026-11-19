"""Finding the Tailscale address safely, keeping the page on it, and the launchd plist."""
import importlib
import plistlib
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.guardian_v1_tailscale import (
    TailscaleWatcher, find_tailscale_address, parse_tailscale_address)

MAC_IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
\tinet6 ::1 prefixlen 128
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether 3c:22:fb:00:00:01
\tinet 192.168.1.10 netmask 0xffffff00 broadcast 192.168.1.255
utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet6 fe80::1%utun0 prefixlen 64 scopeid 0xe
utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1280
\tinet 100.100.1.2 --> 100.100.1.2 netmask 0xffffffff
\tinet6 fd7a:115c:a1e0::1/128 prefixlen 128
"""


def test_the_real_mac_output_gives_the_tailscale_address():
    assert parse_tailscale_address(MAC_IFCONFIG) == "100.100.1.2"


def test_a_provider_side_100_address_on_the_ordinary_interface_is_never_used():
    text = ("en0: flags=8863<UP> mtu 1500\n\tinet 100.64.5.5 netmask 0xffc00000\n"
            "utun4: flags=8051<UP> mtu 1280\n\tinet6 fd7a::1/128 prefixlen 128\n")
    assert parse_tailscale_address(text) is None


def test_other_addresses_on_a_utun_interface_are_ignored():
    for address in ("10.8.0.2", "192.168.1.5", "100.200.1.1", "100.63.0.1"):
        text = f"utun5: flags=8051<UP> mtu 1380\n\tinet {address} --> {address} netmask 0xffffffff\n"
        assert parse_tailscale_address(text) is None, address


def test_nothing_found_means_none():
    for text in ("", "garbage", "lo0: flags=1\n\tinet 127.0.0.1 netmask 0xff000000\n", None):
        assert parse_tailscale_address(text) is None


def test_find_runs_ifconfig_and_never_raises():
    def ok(cmd, **kwargs):
        assert cmd == ["/sbin/ifconfig"]
        return SimpleNamespace(returncode=0, stdout=MAC_IFCONFIG)
    assert find_tailscale_address(ok) == "100.100.1.2"
    for failure in (FileNotFoundError(), subprocess.TimeoutExpired("x", 5), OSError()):
        def bad(cmd, **kwargs):
            raise failure
        assert find_tailscale_address(bad) is None
    assert find_tailscale_address(lambda c, **k: SimpleNamespace(returncode=1, stdout=MAC_IFCONFIG)) is None


class FakeServer:
    def __init__(self, address):
        self.address, self.closed = address, False
        self.server_address = (address, 8765)

    def shutdown(self):
        self.closed = True

    def server_close(self):
        pass


def make_watcher(addresses, fail_for=()):
    said, started = [], []
    queue = list(addresses)

    def detect():
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(value, Exception):
            raise value
        return value

    def start(address):
        if address in fail_for:
            raise OSError(49, "Can't assign requested address")
        server = FakeServer(address)
        started.append(server)
        return server

    return TailscaleWatcher(detect=detect, start=start, say=said.append), said, started


def test_the_page_waits_for_tailscale_then_serves_on_it_once():
    watcher, said, started = make_watcher([None, None, "100.100.1.2"])
    watcher.check_once()
    watcher.check_once()
    assert started == [] and sum("not found yet" in line for line in said) == 1
    watcher.check_once()
    watcher.check_once()   # same address again: nothing new
    assert [s.address for s in started] == ["100.100.1.2"]
    assert any("http://100.100.1.2:8765" in line for line in said)


def test_a_bind_failure_keeps_trying_and_never_crashes():
    watcher, said, started = make_watcher(["100.100.1.2"], fail_for=("100.100.1.2",))
    for _ in range(3):
        watcher.check_once()
    assert started == [] and watcher.server is None
    assert sum("Could not listen" in line for line in said) == 1


def test_a_detection_error_is_treated_as_not_found():
    watcher, said, started = make_watcher([RuntimeError("boom"), "100.64.0.9"])
    watcher.check_once()
    assert started == []
    watcher.check_once()
    assert [s.address for s in started] == ["100.64.0.9"]


def test_a_changed_address_moves_the_server_and_closes_the_old_one():
    watcher, said, started = make_watcher(["100.64.0.9", "100.77.1.1"])
    watcher.check_once()
    watcher.check_once()
    assert [s.address for s in started] == ["100.64.0.9", "100.77.1.1"]
    assert started[0].closed is True and started[1].closed is False
    assert any("changed to 100.77.1.1" in line for line in said)


def test_losing_tailscale_after_it_was_found_keeps_the_server():
    watcher, said, started = make_watcher(["100.64.0.9", None])
    watcher.check_once()
    watcher.check_once()
    assert started[0].closed is False and watcher.server is started[0]


def test_the_watch_loop_stops_when_asked():
    watcher, _said, _started = make_watcher([None])
    stop = threading.Event()
    stop.set()
    watcher.run(stop)  # returns immediately


# --- the page's "auto" option and the launchd plist ---------------------------

def cli():
    return importlib.import_module("guardian_v1_web")


def test_auto_makes_a_watcher_and_an_explicit_address_does_not(tmp_path):
    g = cli()
    base = ["--operator-socket", str(tmp_path / "s"), "--log-dir", str(tmp_path), "--port", "0"]
    assert g.make_watcher(g.parse_args(base + ["--tailscale-address", "auto"]), say=print) is not None
    assert g.make_watcher(g.parse_args(base + ["--tailscale-address", "100.64.0.9"])) is None
    assert g.make_watcher(g.parse_args(base)) is None


def test_auto_starts_loopback_only_and_waits(tmp_path):
    g, said = cli(), []
    servers = g.start_servers(g.parse_args(
        ["--operator-socket", str(tmp_path / "s"), "--log-dir", str(tmp_path), "--port", "0",
         "--tailscale-address", "auto"]), say=said.append)
    try:
        assert len(servers) == 1 and servers[0].server_address[0] == "127.0.0.1"
        assert not any("NOT listening" in line for line in said)
    finally:
        servers[0].server_close()


def launchd():
    return importlib.import_module("guardian_v1_web_launchd")


def test_the_plist_keeps_the_page_running_with_absolute_paths():
    mod = launchd()
    data = plistlib.loads(plistlib.dumps(mod.build_plist(
        python="/Users/x/ObservatorySupervisor/.venv/bin/python",
        project="/Users/x/ObservatorySupervisor",
        allow_hosts=["Marks-Mini"], support="/Users/x/Library/Application Support/GuardianV1")))
    assert data["Label"] == "org.guardian.v1.web"
    assert data["RunAtLoad"] is True and data["KeepAlive"] is True and data["ThrottleInterval"] == 10
    args = data["ProgramArguments"]
    assert args[0].endswith("/.venv/bin/python") and args[1].endswith("/guardian_v1_web.py")
    assert args[args.index("--tailscale-address") + 1] == "auto"
    assert args[args.index("--allow-host") + 1] == "marks-mini"
    assert args[args.index("--operator-socket") + 1].endswith("GuardianV1/operator.sock")
    assert all(a.startswith("/") for a in args if "/" in a)
    assert data["WorkingDirectory"] == "/Users/x/ObservatorySupervisor"


def test_the_plist_can_be_loopback_only_and_rejects_bad_input():
    mod = launchd()
    args = mod.build_plist(python="/a/python", project="/a", tailscale=False)["ProgramArguments"]
    assert "--tailscale-address" not in args
    with pytest.raises(ValueError):
        mod.build_plist(python="relative/python", project="/a")
    with pytest.raises(ValueError):
        mod.build_plist(python="/a/python", project="/a", allow_hosts=["evil.example:80"])


def test_the_plist_writer_never_overwrites_and_never_starts_anything(tmp_path):
    mod = launchd()
    target = tmp_path / "launchd" / "org.guardian.v1.web.plist"
    mod.main(["--output", str(target), "--python", "/a/python"])
    assert plistlib.loads(target.read_bytes())["Label"] == "org.guardian.v1.web"
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        mod.main(["--output", str(target), "--python", "/a/python"])
    assert target.read_bytes() == before
    source = (Path(__file__).resolve().parent.parent / "guardian_v1_web_launchd.py").read_text()
    assert "launchctl" not in source.replace('"launchctl bootstrap', "") or "subprocess" not in source
    assert "subprocess" not in source
