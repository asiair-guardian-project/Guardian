from modules.guardian_types import SafetyPowerResult
from modules.guardian_v1_execution import GuardianV1Execution
from modules.guardian_v1_mode import GuardianV1Mode


def test_monitor_only_does_not_call_hardware_executor():
    mode = GuardianV1Mode()
    calls = []

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=lambda action: calls.append(action),
    )

    result = execution.execute_action("TEST_ACTION")

    assert calls == []
    assert result is SafetyPowerResult.SIMULATED


def test_enabled_mode_calls_hardware_executor():
    mode = GuardianV1Mode()
    mode.enable_hardware_execution()

    calls = []

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=lambda action: (
            calls.append(action)
            or SafetyPowerResult.VERIFIED_OFF
        ),
    )

    result = execution.execute_action("TEST_ACTION")

    assert calls == ["TEST_ACTION"]
    assert result is SafetyPowerResult.VERIFIED_OFF


def test_monitor_only_does_not_call_safety_power_batch_executor():
    mode = GuardianV1Mode()
    calls = []

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=lambda action: None,
        execute_safety_power=lambda roles: calls.append(roles),
    )

    result = execution.execute_safety_power({"ASIAIR", "MOUNT"})

    assert calls == []
    assert len(result) == 2
    assert {record.role for record in result} == {"ASIAIR", "MOUNT"}
    assert all(
        record.endpoint is None
        for record in result
    )
    assert all(
        record.result is SafetyPowerResult.SIMULATED
        for record in result
    )


def test_enabled_mode_calls_safety_power_batch_executor():
    mode = GuardianV1Mode()
    mode.enable_hardware_execution()

    calls = []
    expected = ["batch-result"]

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=lambda action: None,
        execute_safety_power=lambda roles: (
            calls.append(roles)
            or expected
        ),
    )

    result = execution.execute_safety_power({"ASIAIR", "MOUNT"})

    assert calls == [{"ASIAIR", "MOUNT"}]
    assert result == expected


def test_shadow_mode_runtime_protection_never_reaches_hardware():
    from modules.capability_model import REQUIRED_CAPABILITIES
    from modules.commissioning import (
        CommissioningResult,
        CommissioningStatus,
        REQUIRED_COMMISSIONING_CHECKS,
    )
    from modules.guardian_types import (
        AsiairState,
        CapabilityStatus,
        MountMotionState,
        RoofState,
        SessionState,
    )
    from modules.runtime_supervisor import RuntimeSupervisor

    mode = GuardianV1Mode()
    hardware_calls = []

    execution = GuardianV1Execution(
        mode=mode,
        execute_action=lambda action: hardware_calls.append(
            ("action", action)
        ),
        execute_safety_power=lambda roles: hardware_calls.append(
            ("safety_power", roles)
        ),
    )

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in REQUIRED_COMMISSIONING_CHECKS
        },
        configuration_fingerprint="config-a",
    )

    capabilities = {
        capability: CapabilityStatus.AVAILABLE
        for capability in REQUIRED_CAPABILITIES
    }

    supervisor = RuntimeSupervisor()

    # First cycle establishes an active imaging session.
    first = supervisor.evaluate(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        commissioning=commissioning,
        configuration_fingerprint="config-a",
        capability_statuses=capabilities,
        execute_action=execution.execute_action,
        execute_safety_power=execution.execute_safety_power,
    )

    assert first.session.state is SessionState.IMAGING_PERMITTED
    assert hardware_calls == []

    # Roof loss now requires protection.
    second = supervisor.evaluate(
        armed=True,
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        commissioning=commissioning,
        configuration_fingerprint="config-a",
        capability_statuses=capabilities,
        execute_action=execution.execute_action,
        execute_safety_power=execution.execute_safety_power,
    )

    assert second.session.state is SessionState.ABORTED
    assert second.incident is not None
    assert hardware_calls == []

    # Simulated actions cannot satisfy real shutdown requirements.
    # No physical command was issued, so all three power actions remain unresolved.
    from modules.guardian_types import ProtectionAction

    assert set(second.incident.unresolved_actions) == {
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    }

    simulated_power_records = [
        record
        for record in second.incident.records
        if record.action in second.incident.unresolved_actions
    ]
    assert simulated_power_records
    assert all(
        record.result is SafetyPowerResult.SIMULATED
        for record in simulated_power_records
    )

    # Repeated protection evaluation must remain hardware-free.
    for _ in range(3):
        repeated = supervisor.evaluate(
            armed=True,
            roof_state=RoofState.CLOSED,
            asiair_state=AsiairState.ONLINE,
            commissioning=commissioning,
            configuration_fingerprint="config-a",
            capability_statuses=capabilities,
            execute_action=execution.execute_action,
            execute_safety_power=execution.execute_safety_power,
        )

        assert repeated.session.state is SessionState.ABORTED
        assert repeated.incident is second.incident
        assert hardware_calls == []
        assert set(repeated.incident.unresolved_actions) == {
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
        }
