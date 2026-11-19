"""Whole integrated owner gate -> observation -> protection -> Kasa -> durable ACK.
All adapters simulated; never accesses real network or hardware.
"""
from datetime import datetime, timezone

from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import CommissioningResult, CommissioningStatus, REQUIRED_COMMISSIONING_CHECKS
from modules.guardian_types import RoofState, SafetyPowerState, SessionState
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_operator_commands import OperatorCommandHandler
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_starfront_kasa_integration import compose_starfront_kasa_integration
from modules.observatory_safety import ObservatorySafetyObservation

FINGERPRINT = 'simulation-only-fingerprint'

class FakeKasa:
    def __init__(self):
        self.states = {2: SafetyPowerState.ON, 3: SafetyPowerState.ON, 4: SafetyPowerState.ON}
        self.commands = []
    def check_outlet(self, number, alias):
        return (number, alias) in {(2, 'ASIAIR'), (3, 'Wave 150i'), (4, 'Pegasus')}
    def get_outlet_state(self, number, alias):
        return self.states[number]
    def power_off_outlet(self, number, alias):
        self.commands.append(number)
        self.states[number] = SafetyPowerState.OFF
        return True

class FakeAsiair:
    def is_reachable(self):
        return True

class FakeRoof:
    def __init__(self):
        self.state = RoofState.OPEN
    def observe(self):
        return ObservatorySafetyObservation(state=self.state, observed_at=datetime.now(timezone.utc))

def test_integrated_roof_abort_shutdown_persistence_and_ack(tmp_path):
    store = GuardianV1RecoveryStore(tmp_path / 'simulated_recovery.json')
    from modules.runtime_supervisor import RuntimeSupervisor
    store.write(RuntimeSupervisor().export_recovery_state())
    app = GuardianV1Application(configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store)
    kasa, roof = FakeKasa(), FakeRoof()
    commissioning = CommissioningStatus(
        results={check: CommissioningResult.VERIFIED for check in REQUIRED_COMMISSIONING_CHECKS},
        configuration_fingerprint=FINGERPRINT,
    )
    runtime = compose_starfront_kasa_integration(
        application=app, asiair_host='example.invalid', alpaca_host='example.invalid',
        alpaca_port=443, alpaca_device_number=17, kasa_host='example.invalid',
        commissioning=commissioning, configuration_fingerprint=FINGERPRINT,
        kasa_transport=kasa, asiair_adapter=FakeAsiair(), observatory_adapter=roof,
    )
    gate = GuardianV1ArmedGate(application=app, observation_runtime=runtime)
    assert not gate.arm()
    app.mode.enable_hardware_execution()  # isolated test instance, never production
    assert gate.arm()
    first = gate.cycle(now=datetime.now(timezone.utc))
    assert first.evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []
    roof.state = RoofState.CLOSED
    second = gate.cycle(now=datetime.now(timezone.utc))
    assert second.evaluation.session.state is SessionState.ABORTED
    assert sorted(kasa.commands) == [2, 3, 4]
    assert not gate.armed
    assert not gate.arm()
    assert store.read()['active_incident'] is not None
    restarted = GuardianV1Application(configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store)
    assert restarted.supervisor.incident is not None
    assert restarted.supervisor.session_state is SessionState.ABORTED
    handler = OperatorCommandHandler(restarted)
    token = handler.current_incident_token()
    response = handler.handle({'command': 'ACKNOWLEDGE_ABORT', 'incident_id': token, 'confirmed': True})
    assert response.ok, response
    assert store.read()['abort_acknowledged'] is True
    assert restarted.supervisor.incident is not None
    assert sorted(kasa.commands) == [2, 3, 4]
