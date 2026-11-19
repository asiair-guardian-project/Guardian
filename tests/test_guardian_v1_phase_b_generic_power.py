"""Phase B: controller-neutral safety-power contract; fake adapters only."""
import pytest
from modules.guardian_types import SafetyPowerResult, SafetyPowerRole
from modules.safety_power import SafetyPowerEndpoint, SafetyPowerTopology
from modules.safety_power_manager import SafetyPowerManager, SafetyPowerRoutingError


class FakeController:
    def __init__(self, controller_id, *, verified=True, failure=None):
        self._id = controller_id
        self._verified = verified
        self.failure = failure
        self.commands = []

    @property
    def controller_id(self):
        return self._id

    @property
    def supports_verification(self):
        return self._verified

    def power_off(self, endpoint):
        self.commands.append(endpoint.endpoint_id)
        if self.failure == 'command':
            return SafetyPowerResult.FAILED
        if self.failure == 'exception':
            raise RuntimeError('simulated controller outage')
        return SafetyPowerResult.COMMANDED_UNVERIFIED

    def verify_off(self, endpoint):
        if self.failure == 'verification':
            return SafetyPowerResult.FAILED
        if self.failure == 'verification_exception':
            raise RuntimeError('simulated readback outage')
        return SafetyPowerResult.VERIFIED_OFF


def test_controller_neutral_routing_and_verification():
    for controller_id in ('kasa-simulated', 'digital-loggers-simulated'):
        adapter = FakeController(controller_id)
        endpoint = SafetyPowerEndpoint(controller_id, 'outlet-2')
        assert SafetyPowerManager({controller_id: adapter}).power_off(endpoint) is SafetyPowerResult.VERIFIED_OFF
        assert adapter.commands == ['outlet-2']


@pytest.mark.parametrize('failure', ['command', 'exception', 'verification', 'verification_exception'])
def test_failure_is_not_reported_as_verified_off(failure):
    adapter = FakeController('fake', failure=failure)
    endpoint = SafetyPowerEndpoint('fake', 'outlet-2')
    manager = SafetyPowerManager({'fake': adapter})
    if failure == 'exception':
        with pytest.raises(RuntimeError):
            manager.power_off(endpoint)
    else:
        assert manager.power_off(endpoint) is SafetyPowerResult.FAILED


def test_unverified_controller_is_not_accepted_as_verified():
    adapter = FakeController('fake', verified=False)
    endpoint = SafetyPowerEndpoint('fake', 'outlet-2')
    assert SafetyPowerManager({'fake': adapter}).power_off(endpoint) is SafetyPowerResult.COMMANDED_UNVERIFIED


def test_unconfigured_controller_refused_without_commands():
    adapter = FakeController('configured')
    endpoint = SafetyPowerEndpoint('unconfigured', 'outlet-2')
    with pytest.raises(SafetyPowerRoutingError):
        SafetyPowerManager({'configured': adapter}).power_off(endpoint)
    assert adapter.commands == []


def test_missing_role_is_reported_failed_without_touching_host():
    adapter = FakeController('fake')
    asiair = SafetyPowerEndpoint('fake', 'outlet-2')
    host = SafetyPowerEndpoint('fake', 'outlet-1')
    topology = SafetyPowerTopology({SafetyPowerRole.ASIAIR: asiair, SafetyPowerRole.GUARDIAN_HOST: host})
    records = SafetyPowerManager({'fake': adapter}).power_off_roles(
        {SafetyPowerRole.ASIAIR, SafetyPowerRole.MOUNT}, topology, {}, {}
    )
    results = {r.role: r.result for r in records}
    assert results[SafetyPowerRole.ASIAIR] is SafetyPowerResult.VERIFIED_OFF
    assert results[SafetyPowerRole.MOUNT] is SafetyPowerResult.FAILED
    assert adapter.commands == ['outlet-2']
