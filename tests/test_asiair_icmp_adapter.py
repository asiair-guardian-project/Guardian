from types import SimpleNamespace

import pytest

from modules.asiair_icmp_adapter import AsiairIcmpAdapter


def test_ping_success_is_reachable(monkeypatch):
    monkeypatch.setattr(
        "modules.asiair_icmp_adapter.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )

    assert AsiairIcmpAdapter("asiair.local").is_reachable()


def test_ping_no_reply_is_unreachable(monkeypatch):
    monkeypatch.setattr(
        "modules.asiair_icmp_adapter.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    assert not AsiairIcmpAdapter("asiair.local").is_reachable()


def test_ping_execution_error_raises_monitoring_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("ping executable unavailable")

    monkeypatch.setattr(
        "modules.asiair_icmp_adapter.subprocess.run",
        fail,
    )

    with pytest.raises(RuntimeError):
        AsiairIcmpAdapter("asiair.local").is_reachable()


def test_unexpected_ping_return_code_raises_monitoring_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        "modules.asiair_icmp_adapter.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2),
    )

    with pytest.raises(RuntimeError):
        AsiairIcmpAdapter("asiair.local").is_reachable()


def test_adapter_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        AsiairIcmpAdapter("")

    with pytest.raises(ValueError):
        AsiairIcmpAdapter("asiair.local", timeout_seconds=0)


MAC_NO_REPLY = (
    "PING 192.168.1.20 (192.168.1.20): 56 data bytes\n"
    "Request timeout for icmp_seq 0\n\n"
    "--- 192.168.1.20 ping statistics ---\n"
    "3 packets transmitted, 0 packets received, 100.0% packet loss\n"
)
LINUX_NO_REPLY = (
    "--- x ping statistics ---\n"
    "1 packets transmitted, 0 received, 100% packet loss, time 0ms\n"
)


def _ping(monkeypatch, code, out=""):
    monkeypatch.setattr(
        "modules.asiair_icmp_adapter.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=code, stdout=out),
    )


def test_macos_no_reply_exit_2_is_unreachable_not_a_broken_probe(monkeypatch):
    _ping(monkeypatch, 2, MAC_NO_REPLY)
    assert AsiairIcmpAdapter("192.168.1.20").is_reachable() is False


def test_linux_no_reply_exit_1_with_statistics_is_unreachable(monkeypatch):
    _ping(monkeypatch, 1, LINUX_NO_REPLY)
    assert AsiairIcmpAdapter("x").is_reachable() is False


def test_unknown_host_is_a_probe_failure_not_a_lost_asiair(monkeypatch):
    _ping(monkeypatch, 68, "ping: cannot resolve asiair.local: Unknown host\n")
    with pytest.raises(RuntimeError):
        AsiairIcmpAdapter("asiair.local").is_reachable()


def test_exit_2_without_statistics_still_raises(monkeypatch):
    _ping(monkeypatch, 2, "")
    with pytest.raises(RuntimeError):
        AsiairIcmpAdapter("x").is_reachable()


def test_replies_received_but_nonzero_exit_is_inconsistent_and_raises(monkeypatch):
    _ping(monkeypatch, 2, "3 packets transmitted, 2 packets received, 33.3% packet loss\n")
    with pytest.raises(RuntimeError):
        AsiairIcmpAdapter("x").is_reachable()


def test_zero_exit_is_reachable_even_with_statistics(monkeypatch):
    _ping(monkeypatch, 0, "3 packets transmitted, 3 packets received, 0.0% packet loss\n")
    assert AsiairIcmpAdapter("x").is_reachable() is True


def test_process_timeout_leaves_room_for_macos_ping_overrun(monkeypatch):
    """macOS ping with -W 2000 and no reply takes ~3.02 s in practice."""
    seen = {}

    def fake_run(*a, **k):
        seen["timeout"] = k["timeout"]
        return SimpleNamespace(returncode=2, stdout=MAC_NO_REPLY)

    monkeypatch.setattr("modules.asiair_icmp_adapter.subprocess.run", fake_run)
    AsiairIcmpAdapter("192.168.1.20", timeout_seconds=2.0).is_reachable()
    assert seen["timeout"] >= 2.0 + 3.0


def test_a_hung_ping_is_still_a_probe_failure(monkeypatch):
    import subprocess

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("ping", 6.0)

    monkeypatch.setattr("modules.asiair_icmp_adapter.subprocess.run", hang)
    with pytest.raises(RuntimeError):
        AsiairIcmpAdapter("x").is_reachable()
