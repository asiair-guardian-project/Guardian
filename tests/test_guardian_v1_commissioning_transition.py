"""Simulated commissioning-to-ARM transitions; no physical power operations."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from modules.commissioning import (
    CommissioningCheck, CommissioningResult, CommissioningStatus,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.guardian_types import SessionState
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_mode import GuardianV1Mode

FINGERPRINT = 'simulated-starfront-config'


class FakeRuntime:
    _configuration_fingerprint = FINGERPRINT

    def __init__(self, commissioning):
        self._commissioning = commissioning
        self.cycles = []
        self.fail = False
        self.abort_on_cycle = False
        self.application = None

    def run_cycle(self, *, armed, now):
        if self.fail:
            raise OSError('simulated observation failure')
        self.cycles.append(armed)
        if self.abort_on_cycle and armed:
            self.application.supervisor.incident = object()
        return armed


def make_runtime(results=None, fingerprint=FINGERPRINT):
    commissioning = CommissioningStatus(
        results=results or {}, configuration_fingerprint=fingerprint,
    )
    app = SimpleNamespace(
        mode=GuardianV1Mode(),
        supervisor=SimpleNamespace(
            incident=None, recovery_blocked=False,
            session_state=SessionState.DISARMED,
        ),
        recovery_store=object(),
    )
    runtime = FakeRuntime(commissioning)
    runtime.application = app
    gate = GuardianV1ArmedGate(application=app, observation_runtime=runtime)
    return app, runtime, gate


def verified_results():
    return {check: CommissioningResult.VERIFIED for check in REQUIRED_COMMISSIONING_CHECKS}


def test_uncommissioned_cannot_arm_even_with_hardware_enabled():
    app, runtime, gate = make_runtime()
    app.mode.enable_hardware_execution()
    assert not gate.arm()
    assert not gate.armed
    assert runtime.cycles == []


@pytest.mark.parametrize('missing', list(REQUIRED_COMMISSIONING_CHECKS))
def test_each_commissioning_check_is_mandatory(missing):
    results = verified_results()
    results[missing] = CommissioningResult.NOT_TESTED
    app, runtime, gate = make_runtime(results)
    app.mode.enable_hardware_execution()
    assert not gate.arm(), missing


def test_wrong_configuration_fingerprint_blocks_arm():
    app, runtime, gate = make_runtime(verified_results(), fingerprint='other-configuration')
    app.mode.enable_hardware_execution()
    assert not gate.arm()


def test_explicit_enable_then_arm_then_disarm():
    app, runtime, gate = make_runtime(verified_results())
    assert not gate.arm()  # commissioning alone cannot enable hardware
    app.mode.enable_hardware_execution()  # simulated explicit operator commissioning step
    assert gate.arm()
    assert gate.cycle(now=datetime.now(timezone.utc)) is True
    gate.disarm()
    assert not gate.armed
    assert gate.cycle(now=datetime.now(timezone.utc)) is False
    assert runtime.cycles == [True, False]


def test_emergency_abort_latches_and_blocks_rearm():
    app, runtime, gate = make_runtime(verified_results())
    app.mode.enable_hardware_execution()
    assert gate.arm()
    runtime.abort_on_cycle = True
    gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.supervisor.incident is not None
    assert not gate.arm()


def test_recovery_block_prevents_new_arm():
    app, runtime, gate = make_runtime(verified_results())
    app.mode.enable_hardware_execution()
    app.supervisor.recovery_blocked = True
    assert not gate.arm()


def test_observation_failure_disarms_and_disables_execution():
    app, runtime, gate = make_runtime(verified_results())
    app.mode.enable_hardware_execution()
    assert gate.arm()
    runtime.fail = True
    with pytest.raises(OSError, match='simulated observation failure'):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.monitor_only


def test_commissioning_invalidation_disarms_and_disables_execution():
    app, runtime, gate = make_runtime(verified_results())
    app.mode.enable_hardware_execution()
    assert gate.arm()
    runtime._commissioning = CommissioningStatus(
        results=verified_results(), configuration_fingerprint='changed-hardware'
    )
    with pytest.raises(RuntimeError, match='Commissioning invalidated'):
        gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert app.mode.monitor_only
    assert runtime.cycles == []
