"""Safety regression tests for Guardian 1.0 simulated ARMED mode."""

from modules.guardian_v1_execution import GuardianV1Execution
from modules.guardian_v1_mode import GuardianV1Mode
from modules.guardian_types import SafetyPowerResult


def forbidden(*args, **kwargs):
    raise AssertionError("PHYSICAL HARDWARE CALLBACK WAS INVOKED")


def test_simulated_mount_actions_never_reach_hardware():
    mode = GuardianV1Mode()
    assert mode.monitor_only

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=forbidden,
        execute_safety_power=forbidden,
    )

    # Simulate an initial protection attempt and repeated retries.
    for _ in range(5):
        result = execution.execute_action("STOP_WAVE")
        assert result is SafetyPowerResult.SIMULATED


def test_simulated_safety_power_never_reaches_hardware():
    mode = GuardianV1Mode()
    assert mode.monitor_only

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=forbidden,
        execute_safety_power=forbidden,
    )

    for _ in range(5):
        records = execution.execute_safety_power([])

        assert records == []


def test_shadow_mode_has_no_hardware_execution():
    mode = GuardianV1Mode()

    assert mode.monitor_only
    assert not mode.hardware_execution_enabled
