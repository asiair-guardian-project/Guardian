from modules.guardian_types import (
    AsiairState,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SessionState,
)
from modules.protection_evaluator import evaluate_protection_triggers


def evaluate(
    roof_state=RoofState.OPEN,
    asiair_state=AsiairState.ONLINE,
    capability_statuses=None,
    session_state=SessionState.IMAGING_PERMITTED,
):
    if capability_statuses is None:
        capability_statuses = [CapabilityStatus.AVAILABLE]

    return evaluate_protection_triggers(
        session_state=session_state,
        roof_state=roof_state,
        asiair_state=asiair_state,
        required_capability_statuses=capability_statuses,
    )


def test_normal_imaging_has_no_trigger():
    assert evaluate() == set()


def test_closed_roof_with_asiair_online_triggers_roof_protection():
    assert evaluate(
        roof_state=RoofState.CLOSED,
    ) == {ProtectionTrigger.ROOF_CLOSED}


def test_open_roof_with_established_asiair_loss_triggers_protection():
    assert evaluate(
        asiair_state=AsiairState.LOST,
    ) == {ProtectionTrigger.ASIAIR_LOST}


def test_roof_unknown_alone_is_not_a_trigger():
    assert evaluate(
        roof_state=RoofState.UNKNOWN,
    ) == set()


def test_required_capability_unknown_triggers_capability_loss():
    assert evaluate(
        capability_statuses=[CapabilityStatus.UNKNOWN],
    ) == {ProtectionTrigger.PROTECTION_CAPABILITY_LOST}


def test_required_capability_failed_triggers_capability_loss():
    assert evaluate(
        capability_statuses=[CapabilityStatus.FAILED],
    ) == {ProtectionTrigger.PROTECTION_CAPABILITY_LOST}


def test_required_capability_unavailable_triggers_capability_loss():
    assert evaluate(
        capability_statuses=[CapabilityStatus.UNAVAILABLE],
    ) == {ProtectionTrigger.PROTECTION_CAPABILITY_LOST}


def test_multiple_triggers_can_be_reported_together():
    assert evaluate(
        roof_state=RoofState.CLOSED,
        capability_statuses=[CapabilityStatus.FAILED],
    ) == {
        ProtectionTrigger.ROOF_CLOSED,
        ProtectionTrigger.PROTECTION_CAPABILITY_LOST,
    }


def test_waiting_session_does_not_generate_active_imaging_trigger():
    assert evaluate(
        roof_state=RoofState.CLOSED,
        session_state=SessionState.WAITING_FOR_ROOF,
    ) == set()


def test_aborted_session_does_not_generate_new_initial_trigger():
    assert evaluate(
        roof_state=RoofState.CLOSED,
        session_state=SessionState.ABORTED,
    ) == set()


def test_closed_roof_and_lost_asiair_both_trigger_protection():
    assert evaluate(
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.LOST,
    ) == {
        ProtectionTrigger.ROOF_CLOSED,
        ProtectionTrigger.ASIAIR_LOST,
    }
