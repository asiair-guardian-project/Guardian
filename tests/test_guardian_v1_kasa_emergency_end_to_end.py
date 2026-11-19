"""Full Guardian decision -> Kasa routing test, entirely simulated hardware.

Never connects to an HS300, alters launchd, or changes recovery.json.
"""
import pytest

from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import (
    CommissioningResult, CommissioningStatus, REQUIRED_COMMISSIONING_CHECKS,
)
from modules.guardian_types import (
    AsiairState, CapabilityStatus, RoofState, SafetyPowerResult,
    SafetyPowerState, SessionState,
)
from modules.guardian_v1_execution import GuardianV1Execution
from modules.guardian_v1_mode import GuardianV1Mode
from modules.guardian_v1_starfront_kasa import compose_starfront_kasa
from modules.runtime_supervisor import RuntimeSupervisor


class FakeKasaTransport:
    def __init__(self):
        self.states = {2: SafetyPowerState.ON, 3: SafetyPowerState.ON,
                       4: SafetyPowerState.ON}
        self.commands = []

    def check_outlet(self, number, alias):
        return (number, alias) in {
            (2, 'ASIAIR'), (3, 'Wave 150i'), (4, 'Pegasus')
        }

    def get_outlet_state(self, number, alias):
        assert self.check_outlet(number, alias)
        return self.states[number]

    def power_off_outlet(self, number, alias):
        assert self.check_outlet(number, alias)
        self.commands.append((number, alias))
        self.states[number] = SafetyPowerState.OFF
        return True


@pytest.mark.parametrize('trigger', ['roof', 'asiair'])
def test_armed_emergency_executes_three_verified_shutdowns(trigger):
    kasa = FakeKasaTransport()
    wiring = compose_starfront_kasa(host='example.invalid', transport=kasa)
    mode = GuardianV1Mode()
    mode.enable_hardware_execution()  # Local test object only, never production.
    execution = GuardianV1Execution(
        mode=mode,
        execute_action=lambda action: SafetyPowerResult.FAILED,
        execute_safety_power=wiring.execute_safety_power,
    )
    supervisor = RuntimeSupervisor()
    commissioning = CommissioningStatus(
        results={check: CommissioningResult.VERIFIED
                 for check in REQUIRED_COMMISSIONING_CHECKS},
        configuration_fingerprint='test-only',
    )
    capabilities = {cap: CapabilityStatus.AVAILABLE
                    for cap in REQUIRED_CAPABILITIES}

    def cycle(roof, asiair):
        return supervisor.evaluate(
            armed=True, roof_state=roof, asiair_state=asiair,
            commissioning=commissioning,
            configuration_fingerprint='test-only',
            capability_statuses=capabilities,
            execute_action=execution.execute_action,
            execute_safety_power=execution.execute_safety_power,
        )

    first = cycle(RoofState.OPEN, AsiairState.ONLINE)
    assert first.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []

    second = cycle(
        RoofState.CLOSED if trigger == 'roof' else RoofState.OPEN,
        AsiairState.ONLINE if trigger == 'roof' else AsiairState.LOST,
    )
    assert second.session.state is SessionState.ABORTED
    assert second.incident is not None
    assert set(kasa.commands) == {
        (2, 'ASIAIR'), (3, 'Wave 150i'), (4, 'Pegasus')
    }
    assert len(kasa.commands) == 3
    assert all(state is SafetyPowerState.OFF for state in kasa.states.values())
    assert second.incident.unresolved_actions == set() or not second.incident.unresolved_actions

    repeated = cycle(RoofState.OPEN, AsiairState.ONLINE)
    assert repeated.session.state is SessionState.ABORTED
    assert len(kasa.commands) == 3  # No extra switching after verified OFF.
