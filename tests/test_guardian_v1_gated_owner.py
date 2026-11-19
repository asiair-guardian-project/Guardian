import pytest
from modules.guardian_v1_gated_owner import GuardianV1GatedOwner


class Mode:
    hardware_execution_enabled = False


class App:
    mode = Mode()


class Gate:
    armed = False
    application = App()


def test_rejects_armed_start():
    gate = Gate()
    gate.armed = True
    with pytest.raises(RuntimeError, match="DISARMED"):
        GuardianV1GatedOwner(gate=gate, socket_path="/tmp/unused")


def test_rejects_hardware_enabled_start():
    gate = Gate()
    gate.application = type("A", (), {"mode": type("M", (), {"hardware_execution_enabled": True})()})()
    with pytest.raises(RuntimeError, match="monitor-only"):
        GuardianV1GatedOwner(gate=gate, socket_path="/tmp/unused")


def test_rejects_invalid_interval():
    with pytest.raises(ValueError):
        GuardianV1GatedOwner(gate=Gate(), socket_path="/tmp/unused", interval_seconds=0)


class FakeSocket:
    def __init__(self): self.started = False; self.closed = False
    def start(self): self.started = True
    def serve_once(self): return False
    def close(self): self.closed = True


def test_owner_retries_after_incident_cycle_exception():
    class IncidentGate:
        armed = False
        def __init__(self):
            self.application = type("App", (), {"mode": Mode(), "supervisor": type("Sup", (), {"incident": object()})()})()
            self.calls = 0
        def cycle(self, *, now):
            self.calls += 1
            if self.calls == 1: raise ValueError("incident cycle failed")
    gate = IncidentGate()
    owner = GuardianV1GatedOwner(gate=gate, socket_path="/tmp/unused", interval_seconds=0.01,
                                 clock=iter(range(1000)).__next__, sleep=lambda _: None)
    owner.socket = FakeSocket()
    assert owner.run(cycles=2) == 2
    assert gate.calls == 2
    assert owner.socket.closed


def test_owner_does_not_hide_unexpected_error_without_incident():
    class FailingGate:
        armed = False
        def __init__(self):
            self.application = type("App", (), {"mode": Mode(), "supervisor": type("Sup", (), {"incident": None})()})()
        def cycle(self, *, now): raise ValueError("unexpected")
    owner = GuardianV1GatedOwner(gate=FailingGate(), socket_path="/tmp/unused", interval_seconds=0.01)
    owner.socket = FakeSocket()
    with pytest.raises(ValueError, match="unexpected"):
        owner.run(cycles=1)
    assert owner.socket.closed
