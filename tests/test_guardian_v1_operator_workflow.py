"""Operator workflow regression tests, no hardware or live service."""
from types import SimpleNamespace
from datetime import datetime, timezone
from modules.guardian_types import SessionState
from modules.guardian_v1_mode import GuardianV1Mode
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_gated_owner import GuardianV1GatedOwner


class Commissioning:
    valid = True
    def valid_for_configuration(self, fingerprint):
        return self.valid and fingerprint == "test"

class Runtime:
    _configuration_fingerprint = "test"
    def __init__(self):
        self._commissioning = Commissioning()
        self.calls = []
        self.supervisor = None
    def run_cycle(self, *, armed, now):
        self.calls.append(armed)
        return armed

def make_gate():
    supervisor = SimpleNamespace(
        incident=None, recovery_blocked=False,
        session_state=SessionState.DISARMED,
    )
    app = SimpleNamespace(mode=GuardianV1Mode(), supervisor=supervisor, recovery_store=object())
    runtime = Runtime()
    gate = GuardianV1ArmedGate(application=app, observation_runtime=runtime)
    return gate, runtime, supervisor

def test_owner_exposes_gate_to_operator_socket(tmp_path):
    gate, runtime, supervisor = make_gate()
    owner = GuardianV1GatedOwner(gate=gate, socket_path=tmp_path / "op.sock")
    assert owner.socket.gate is gate
    assert owner.socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARM_BLOCKED"
    assert not gate.armed

def test_arm_disarm_abort_and_recovery_block():
    gate, runtime, supervisor = make_gate()
    socket = GuardianV1GatedOwner(gate=gate, socket_path="/tmp/g1-test.sock").socket
    app = gate.application
    assert socket._handle_arm_command({"command":"ARM","confirmed":False})["code"] == "INVALID_REQUEST"
    assert socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARM_BLOCKED"
    app.mode.enable_hardware_execution()
    runtime._commissioning.valid = False
    assert socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARM_BLOCKED"
    runtime._commissioning.valid = True
    assert socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARMED"
    assert gate.cycle(now=datetime.now(timezone.utc)) is True
    assert socket._handle_arm_command({"command":"DISARM","confirmed":True})["code"] == "DISARMED"
    assert gate.cycle(now=datetime.now(timezone.utc)) is False
    assert socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARMED"
    supervisor.incident = object()
    gate.cycle(now=datetime.now(timezone.utc))
    assert gate.armed is False
    assert socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARM_BLOCKED"
    supervisor.incident = None
    supervisor.recovery_blocked = True
    assert socket._handle_arm_command({"command":"ARM","confirmed":True})["code"] == "ARM_BLOCKED"
