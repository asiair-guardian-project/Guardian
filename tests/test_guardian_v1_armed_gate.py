from types import SimpleNamespace
from datetime import datetime, timezone
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_mode import GuardianV1Mode
from modules.guardian_types import SessionState

class FakeRuntime:
    _configuration_fingerprint = "test"
    def __init__(self, commissioning):
        self._commissioning = commissioning
        self.calls = []
    def run_cycle(self, *, armed, now):
        self.calls.append(armed)
        return armed

class FakeCommissioning:
    def __init__(self, valid): self.valid = valid
    def valid_for_configuration(self, fingerprint): return self.valid and fingerprint == "test"

def setup(valid=True):
    mode = GuardianV1Mode()
    supervisor = SimpleNamespace(incident=None, recovery_blocked=False, session_state=SessionState.DISARMED)
    app = SimpleNamespace(mode=mode, supervisor=supervisor, recovery_store=object())
    runtime = FakeRuntime(FakeCommissioning(valid))
    return app, runtime, GuardianV1ArmedGate(application=app, observation_runtime=runtime)

def test_never_arms_monitor_only():
    app, runtime, gate = setup()
    assert gate.arm() is False
    assert gate.cycle(now=datetime.now(timezone.utc)) is False
    assert runtime.calls == [False]

def test_commissioning_required_even_after_hardware_enabled():
    app, runtime, gate = setup(False)
    app.mode.enable_hardware_execution()
    assert gate.arm() is False

def test_armed_cycle_and_abort_latch():
    app, runtime, gate = setup()
    app.mode.enable_hardware_execution()
    assert gate.arm() is True
    assert gate.cycle(now=datetime.now(timezone.utc)) is True
    app.supervisor.incident = object()
    assert gate.cycle(now=datetime.now(timezone.utc)) is True
    assert gate.armed is False
    assert gate.arm() is False

def test_disarm_is_inert():
    app, runtime, gate = setup()
    app.mode.enable_hardware_execution()
    assert gate.arm()
    gate.disarm()
    assert gate.cycle(now=datetime.now(timezone.utc)) is False


def test_exception_before_incident_disarms_and_disables_execution():
    app, runtime, gate = setup()
    app.mode.enable_hardware_execution()
    assert gate.arm()
    def fail(*, armed, now):
        raise OSError("observation failure")
    runtime.run_cycle = fail
    import pytest
    with pytest.raises(OSError):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.monitor_only


def test_exception_after_incident_preserves_real_shutdown_retry_authority():
    app, runtime, gate = setup()
    saved = []
    app.recovery_store = SimpleNamespace(write=lambda state: saved.append(state))
    app.supervisor.export_recovery_state = lambda: {"active_incident": "latched"}
    app.mode.enable_hardware_execution()
    assert gate.arm()
    def fail_after_latch(*, armed, now):
        app.supervisor.incident = object()
        raise OSError("failed after protection latch")
    runtime.run_cycle = fail_after_latch
    import pytest
    with pytest.raises(OSError):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.hardware_execution_enabled
    assert saved == [{"active_incident": "latched"}]
    assert not gate.arm()


def test_commissioning_invalidated_after_incident_keeps_retry_authority():
    app, runtime, gate = setup()
    app.mode.enable_hardware_execution()
    assert gate.arm()
    app.supervisor.incident = object()
    runtime._commissioning.valid = False
    import pytest
    with pytest.raises(RuntimeError, match="Commissioning invalidated"):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.hardware_execution_enabled
