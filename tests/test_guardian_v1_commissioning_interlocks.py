"""Fail-closed commissioning transition tests; simulated only."""
from datetime import datetime, timezone
import pytest
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_mode import GuardianV1Mode
from modules.guardian_types import SessionState
from types import SimpleNamespace

class FakeCommissioning:
    valid = True
    def valid_for_configuration(self, fingerprint):
        return self.valid and fingerprint == "test"

class FakeRuntime:
    _configuration_fingerprint = "test"
    def __init__(self):
        self._commissioning = FakeCommissioning()
        self.calls = []
    def run_cycle(self, *, armed, now):
        self.calls.append(armed)
        return armed

def setup():
    supervisor = SimpleNamespace(incident=None, recovery_blocked=False, session_state=SessionState.DISARMED)
    app = SimpleNamespace(mode=GuardianV1Mode(), supervisor=supervisor, recovery_store=object())
    runtime = FakeRuntime()
    return app, runtime, GuardianV1ArmedGate(application=app, observation_runtime=runtime)

def test_commissioning_invalidation_disarms_and_disables_hardware():
    app, runtime, gate = setup()
    app.mode.enable_hardware_execution()
    assert gate.arm()
    runtime._commissioning.valid = False
    with pytest.raises(RuntimeError, match="Commissioning invalidated"):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.monitor_only
    assert runtime.calls == []

def test_cycle_failure_disarms_and_disables_hardware():
    app, runtime, gate = setup()
    app.mode.enable_hardware_execution()
    assert gate.arm()
    def fail(*, armed, now):
        raise OSError("observation failed")
    runtime.run_cycle = fail
    with pytest.raises(OSError):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.monitor_only

