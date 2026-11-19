"""Fail-closed Phase B boundary checks. Fake adapters only; no network or hardware."""
from datetime import datetime, timezone

from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import CommissioningStatus
from modules.guardian_types import RoofState, SafetyPowerState
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_starfront_kasa_integration import compose_starfront_kasa_integration
from modules.observatory_safety import ObservatorySafetyObservation
from modules.runtime_supervisor import RuntimeSupervisor


class FakeKasa:
    def __init__(self):
        self.commands = []
    def check_outlet(self, number, alias):
        return (number, alias) in {(2, "ASIAIR"), (3, "Wave 150i"), (4, "Pegasus")}
    def get_outlet_state(self, number, alias):
        return SafetyPowerState.ON
    def power_off_outlet(self, number, alias):
        self.commands.append(number)
        return True


class FakeAsiair:
    def is_reachable(self):
        return True


class FakeRoof:
    def observe(self):
        return ObservatorySafetyObservation(
            state=RoofState.CLOSED, observed_at=datetime.now(timezone.utc)
        )


def _build(tmp_path, commissioning):
    store = GuardianV1RecoveryStore(tmp_path / "isolated_recovery.json")
    store.write(RuntimeSupervisor().export_recovery_state())
    app = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store
    )
    fake = FakeKasa()
    runtime = compose_starfront_kasa_integration(
        application=app, asiair_host="example.invalid",
        alpaca_host="example.invalid", alpaca_port=443,
        alpaca_device_number=17, kasa_host="example.invalid",
        commissioning=commissioning,
        configuration_fingerprint="phase-b-isolated-test",
        kasa_transport=fake, asiair_adapter=FakeAsiair(),
        observatory_adapter=FakeRoof(),
    )
    return app, GuardianV1ArmedGate(application=app, observation_runtime=runtime), fake


def test_uncommissioned_cannot_arm_or_switch_with_hardware_disabled(tmp_path):
    app, gate, fake = _build(tmp_path, CommissioningStatus(results={}))
    assert app.mode.monitor_only
    assert not gate.arm()
    gate.cycle(now=datetime.now(timezone.utc))
    assert not gate.armed
    assert fake.commands == []


def test_uncommissioned_cannot_arm_even_if_isolated_mode_enabled(tmp_path):
    app, gate, fake = _build(tmp_path, CommissioningStatus(results={}))
    app.mode.enable_hardware_execution()  # isolated fake-only app, never deployed
    assert not gate.arm()
    assert not gate.armed
    assert fake.commands == []
    app.mode.disable_hardware_execution()


def test_fingerprint_mismatch_cannot_arm(tmp_path):
    from modules.commissioning import (
        CommissioningResult, REQUIRED_COMMISSIONING_CHECKS
    )
    status = CommissioningStatus(
        results={c: CommissioningResult.VERIFIED for c in REQUIRED_COMMISSIONING_CHECKS},
        configuration_fingerprint="different-configuration",
    )
    app, gate, fake = _build(tmp_path, status)
    app.mode.enable_hardware_execution()  # isolated fake-only app
    assert not gate.arm()
    assert fake.commands == []
    app.mode.disable_hardware_execution()
