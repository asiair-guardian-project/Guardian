from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import (
    CommissioningResult,
    CommissioningStatus,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.guardian_runtime import evaluate_runtime
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    MountMotionState,
    ProtectionAction,
    ProtectionTrigger,
    RoofState,
    SafetyPowerResult,
    SessionState,
)


def commissioned():
    return CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in REQUIRED_COMMISSIONING_CHECKS
        },
        configuration_fingerprint="config-a",
    )


def available_capabilities():
    return {
        capability: CapabilityStatus.AVAILABLE
        for capability in REQUIRED_CAPABILITIES
    }


def evaluate(
    *,
    current_state=SessionState.IMAGING_PERMITTED,
    roof_state=RoofState.OPEN,
    asiair_state=AsiairState.ONLINE,
    capabilities=None,
    execute_action=None,
):
    if capabilities is None:
        capabilities = available_capabilities()

    if execute_action is None:
        execute_action = lambda action: SafetyPowerResult.VERIFIED_OFF

    return evaluate_runtime(
        current_state=current_state,
        armed=True,
        roof_state=roof_state,
        asiair_state=asiair_state,
        commissioning=commissioned(),
        configuration_fingerprint="config-a",
        capability_statuses=capabilities,
        execute_action=execute_action,
    )


def test_normal_active_session_does_not_execute_protection():
    attempted = []

    result = evaluate(
        execute_action=lambda action: attempted.append(action)
    )

    assert result.session.state is SessionState.IMAGING_PERMITTED
    assert result.incident is None
    assert attempted == []


def test_roof_closure_executes_protection_and_aborts():
    attempted = []

    def execute_action(action):
        attempted.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    result = evaluate(
        roof_state=RoofState.CLOSED,
        execute_action=execute_action,
    )

    assert result.session.state is SessionState.ABORTED
    assert result.incident is not None
    assert result.incident.triggers == {ProtectionTrigger.ROOF_CLOSED}
    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]


def test_asiair_loss_executes_protection():
    result = evaluate(asiair_state=AsiairState.LOST)

    assert result.session.state is SessionState.ABORTED
    assert result.incident is not None
    assert result.incident.triggers == {ProtectionTrigger.ASIAIR_LOST}


def test_runtime_capability_loss_executes_protection():
    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = (
        CapabilityStatus.FAILED
    )

    result = evaluate(capabilities=capabilities)

    assert result.session.state is SessionState.ABORTED
    assert result.incident is not None
    assert result.incident.triggers == {
        ProtectionTrigger.PROTECTION_CAPABILITY_LOST
    }


def test_pre_imaging_not_ready_does_not_execute_emergency_actions():
    attempted = []
    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = (
        CapabilityStatus.FAILED
    )

    result = evaluate(
        current_state=SessionState.WAITING_FOR_PROTECTION,
        capabilities=capabilities,
        execute_action=lambda action: attempted.append(action),
    )

    assert result.session.state is SessionState.WAITING_FOR_PROTECTION
    assert result.incident is None
    assert attempted == []


def test_failed_required_power_action_remains_unresolved_after_abort():
    def execute_action(action):
        if action is ProtectionAction.SAFETY_POWER_OFF_MOUNT:
            return SafetyPowerResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    result = evaluate(
        roof_state=RoofState.CLOSED,
        execute_action=execute_action,
    )

    assert result.session.state is SessionState.ABORTED
    assert result.incident is not None
    assert result.incident.session_state is SessionState.ABORTED
    assert result.incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT
    ]


def test_optional_mount_capabilities_do_not_change_power_shutdown():
    attempted = []
    capabilities = available_capabilities()
    capabilities[Capability.INDEPENDENT_MOUNT_STOP] = (
        CapabilityStatus.AVAILABLE
    )
    capabilities[Capability.MOUNT_STOP_VERIFICATION] = (
        CapabilityStatus.AVAILABLE
    )

    result = evaluate(
        roof_state=RoofState.CLOSED,
        capabilities=capabilities,
        execute_action=lambda action: (
            attempted.append(action),
            SafetyPowerResult.VERIFIED_OFF,
        )[1],
    )

    assert result.incident is not None
    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]


def test_incident_records_lost_required_capability():
    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = (
        CapabilityStatus.UNKNOWN
    )

    result = evaluate(capabilities=capabilities)

    assert result.incident is not None
    assert result.incident.lost_capabilities == {
        Capability.SAFETY_POWER_CONTROL
    }


def test_optional_capability_loss_is_not_recorded_as_required_loss():
    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = (
        CapabilityStatus.UNKNOWN
    )
    capabilities[Capability.UPS_MONITORING] = (
        CapabilityStatus.UNKNOWN
    )

    result = evaluate(capabilities=capabilities)

    assert result.incident is not None
    assert result.incident.lost_capabilities == {
        Capability.SAFETY_POWER_CONTROL
    }
