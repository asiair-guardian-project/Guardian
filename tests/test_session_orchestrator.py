from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import (
    CommissioningResult,
    CommissioningStatus,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SessionState,
)
from modules.session_orchestrator import evaluate_session


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
    current_state=SessionState.WAITING_FOR_ROOF,
    armed=True,
    roof_state=RoofState.OPEN,
    asiair_state=AsiairState.ONLINE,
    commissioning=None,
    fingerprint="config-a",
    capabilities=None,
):
    if commissioning is None:
        commissioning = commissioned()

    if capabilities is None:
        capabilities = available_capabilities()

    return evaluate_session(
        current_state=current_state,
        armed=armed,
        roof_state=roof_state,
        asiair_state=asiair_state,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        capability_statuses=capabilities,
    )


def test_ready_pre_imaging_session_permits_imaging():
    result = evaluate()

    assert result.state is SessionState.IMAGING_PERMITTED
    assert result.triggers == frozenset()


def test_pre_imaging_capability_loss_waits_without_emergency():
    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = (
        CapabilityStatus.FAILED
    )

    result = evaluate(capabilities=capabilities)

    assert result.state is SessionState.WAITING_FOR_PROTECTION
    assert result.triggers == frozenset()


def test_active_capability_loss_aborts_instead_of_waiting():
    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = (
        CapabilityStatus.FAILED
    )

    result = evaluate(
        current_state=SessionState.IMAGING_PERMITTED,
        capabilities=capabilities,
    )

    assert result.state is SessionState.ABORTED
    assert result.triggers == frozenset(
        {ProtectionTrigger.PROTECTION_CAPABILITY_LOST}
    )


def test_active_roof_closure_aborts_session():
    result = evaluate(
        current_state=SessionState.IMAGING_PERMITTED,
        roof_state=RoofState.CLOSED,
    )

    assert result.state is SessionState.ABORTED
    assert result.triggers == frozenset(
        {ProtectionTrigger.ROOF_CLOSED}
    )


def test_active_established_asiair_loss_aborts_session():
    result = evaluate(
        current_state=SessionState.IMAGING_PERMITTED,
        asiair_state=AsiairState.LOST,
    )

    assert result.state is SessionState.ABORTED
    assert result.triggers == frozenset(
        {ProtectionTrigger.ASIAIR_LOST}
    )


def test_active_roof_unknown_does_not_abort_by_itself():
    result = evaluate(
        current_state=SessionState.IMAGING_PERMITTED,
        roof_state=RoofState.UNKNOWN,
    )

    assert result.state is SessionState.IMAGING_PERMITTED
    assert result.triggers == frozenset()


def test_aborted_session_remains_latched():
    result = evaluate(
        current_state=SessionState.ABORTED,
        roof_state=RoofState.OPEN,
    )

    assert result.state is SessionState.ABORTED
    assert result.triggers == frozenset()


def test_changed_configuration_waits_before_imaging():
    result = evaluate(fingerprint="config-b")

    assert result.state is SessionState.WAITING_FOR_PROTECTION
    assert result.triggers == frozenset()
