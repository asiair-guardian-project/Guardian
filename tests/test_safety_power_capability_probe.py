from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    SafetyPowerRole,
)
from modules.safety_power import (
    SafetyPowerEndpoint,
    SafetyPowerTopology,
)
from modules.safety_power_capability_probe import (
    probe_safety_power_control,
)


AIR = SafetyPowerEndpoint("controller-1", "air")
MOUNT = SafetyPowerEndpoint("controller-1", "mount")


class FakeSafetyPowerAdapter:
    supports_verification = False

    def __init__(
        self,
        controller_id="controller-1",
        *,
        invalid=frozenset(),
        error=None,
    ):
        self.controller_id = controller_id
        self.invalid = invalid
        self.error = error
        self.checked = []

    def check_endpoint(self, endpoint):
        self.checked.append(endpoint)

        if self.error is not None:
            raise self.error

        return endpoint not in self.invalid

    def power_off(self, endpoint):
        raise AssertionError(
            "capability probe must never switch power"
        )


def topology():
    return SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: AIR,
            SafetyPowerRole.MOUNT: MOUNT,
        }
    )


def test_available_when_all_required_endpoints_validate():
    adapter = FakeSafetyPowerAdapter()

    result = probe_safety_power_control(
        topology=topology(),
        adapters={"controller-1": adapter},
    )

    assert result.capability is Capability.SAFETY_POWER_CONTROL
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation is True
    assert set(adapter.checked) == {AIR, MOUNT}


def test_probe_never_switches_power():
    adapter = FakeSafetyPowerAdapter()

    probe_safety_power_control(
        topology=topology(),
        adapters={"controller-1": adapter},
    )

    assert set(adapter.checked) == {AIR, MOUNT}


def test_invalid_endpoint_is_failed():
    adapter = FakeSafetyPowerAdapter(
        invalid=frozenset({MOUNT})
    )

    result = probe_safety_power_control(
        topology=topology(),
        adapters={"controller-1": adapter},
    )

    assert result.status is CapabilityStatus.FAILED
    assert result.observation is False


def test_communication_failure_is_unknown():
    adapter = FakeSafetyPowerAdapter(
        error=RuntimeError("controller unreachable")
    )

    result = probe_safety_power_control(
        topology=topology(),
        adapters={"controller-1": adapter},
    )

    assert result.status is CapabilityStatus.UNKNOWN
    assert result.observation is None


def test_missing_asiair_endpoint_is_failed():
    incomplete = SafetyPowerTopology(
        {
            SafetyPowerRole.MOUNT: MOUNT,
        }
    )

    result = probe_safety_power_control(
        topology=incomplete,
        adapters={"controller-1": FakeSafetyPowerAdapter()},
    )

    assert result.status is CapabilityStatus.FAILED


def test_missing_mount_endpoint_is_failed():
    incomplete = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: AIR,
        }
    )

    result = probe_safety_power_control(
        topology=incomplete,
        adapters={"controller-1": FakeSafetyPowerAdapter()},
    )

    assert result.status is CapabilityStatus.FAILED


def test_missing_controller_adapter_is_failed():
    result = probe_safety_power_control(
        topology=topology(),
        adapters={},
    )

    assert result.status is CapabilityStatus.FAILED


def test_mismatched_controller_identity_is_failed():
    adapter = FakeSafetyPowerAdapter(
        controller_id="wrong-controller"
    )

    result = probe_safety_power_control(
        topology=topology(),
        adapters={"controller-1": adapter},
    )

    assert result.status is CapabilityStatus.FAILED


def test_shared_endpoint_is_validated_once():
    shared = SafetyPowerEndpoint(
        "controller-1",
        "shared-output",
    )

    shared_topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
        }
    )

    adapter = FakeSafetyPowerAdapter()

    result = probe_safety_power_control(
        topology=shared_topology,
        adapters={"controller-1": adapter},
    )

    assert result.status is CapabilityStatus.AVAILABLE
    assert adapter.checked == [shared]
