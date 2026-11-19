from modules.core_state import abort_active_session, evaluate_pre_imaging_state
from modules.guardian_types import (
    AsiairState,
    RoofState,
    SessionState,
)



def test_disarmed_always_returns_disarmed():
    assert evaluate_pre_imaging_state(
        armed=False,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        installation_ready=True,
    ) is SessionState.DISARMED


def test_closed_roof_waits_for_roof():
    assert evaluate_pre_imaging_state(
        armed=True,
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        installation_ready=True,
    ) is SessionState.WAITING_FOR_ROOF


def test_unknown_roof_waits_for_roof():
    assert evaluate_pre_imaging_state(
        armed=True,
        roof_state=RoofState.UNKNOWN,
        asiair_state=AsiairState.ONLINE,
        installation_ready=True,
    ) is SessionState.WAITING_FOR_ROOF


def test_open_roof_without_required_protection_waits_for_protection():
    assert evaluate_pre_imaging_state(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        installation_ready=False,
    ) is SessionState.WAITING_FOR_PROTECTION


def test_asiair_not_established_waits_for_protection():
    assert evaluate_pre_imaging_state(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.NOT_ESTABLISHED,
        installation_ready=True,
    ) is SessionState.WAITING_FOR_PROTECTION


def test_all_requirements_permit_imaging():
    assert evaluate_pre_imaging_state(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        installation_ready=True,
    ) is SessionState.IMAGING_PERMITTED


def test_protection_trigger_aborts_active_imaging():
    assert abort_active_session(
        current_state=SessionState.IMAGING_PERMITTED,
        protection_triggered=True,
    ) is SessionState.ABORTED


def test_no_trigger_leaves_active_imaging_unchanged():
    assert abort_active_session(
        current_state=SessionState.IMAGING_PERMITTED,
        protection_triggered=False,
    ) is SessionState.IMAGING_PERMITTED


def test_aborted_state_remains_latched():
    assert abort_active_session(
        current_state=SessionState.ABORTED,
        protection_triggered=False,
    ) is SessionState.ABORTED
