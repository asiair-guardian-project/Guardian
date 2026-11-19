from modules.guardian_types import (
    SafetyPowerResult,
    SafetyPowerState,
)
from modules.safety_power import SafetyPowerEndpoint


class FakeCommandOnlyAdapter:
    controller_id = "command-only"
    supports_verification = False

    def check_endpoint(self, endpoint):
        return True

    def power_off(self, endpoint):
        return SafetyPowerResult.COMMANDED_UNVERIFIED


class FakeVerifyingAdapter:
    controller_id = "verifying"
    supports_verification = True

    def check_endpoint(self, endpoint):
        return True

    def power_off(self, endpoint):
        return SafetyPowerResult.COMMANDED_UNVERIFIED

    def get_power_state(self, endpoint):
        return SafetyPowerState.OFF

    def verify_off(self, endpoint):
        return SafetyPowerResult.VERIFIED_OFF


def test_command_only_controller_can_validate_endpoint():
    endpoint = SafetyPowerEndpoint("command-only", "output-1")
    adapter = FakeCommandOnlyAdapter()

    assert adapter.check_endpoint(endpoint) is True


def test_command_only_controller_can_power_off_endpoint():
    endpoint = SafetyPowerEndpoint("command-only", "output-1")
    adapter = FakeCommandOnlyAdapter()

    assert (
        adapter.power_off(endpoint)
        is SafetyPowerResult.COMMANDED_UNVERIFIED
    )


def test_state_controller_reports_explicit_power_state():
    endpoint = SafetyPowerEndpoint("verifying", "output-1")
    adapter = FakeVerifyingAdapter()

    assert adapter.get_power_state(endpoint) is SafetyPowerState.OFF


def test_verifying_controller_can_confirm_endpoint_off():
    endpoint = SafetyPowerEndpoint("verifying", "output-1")
    adapter = FakeVerifyingAdapter()

    assert (
        adapter.verify_off(endpoint)
        is SafetyPowerResult.VERIFIED_OFF
    )
