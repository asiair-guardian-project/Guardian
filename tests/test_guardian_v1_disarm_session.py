"""DISARM ends an established session (it used to leave IMAGING_PERMITTED stuck, blocking ARM)."""

from types import SimpleNamespace

import pytest

from modules.guardian_types import SessionState
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore, RecoveryStateError
from modules.runtime_supervisor import RuntimeSupervisor
from tests.test_guardian_v1_abort_release import Night


def imaging_night():
    night = Night(None)
    night.cycles(3)
    assert night.gate.arm()
    night.cycles(16)
    assert night.app.supervisor.session_state is SessionState.IMAGING_PERMITTED
    return night


def strip(night):
    return (night.folder / "strip.txt").read_text()


def state(night):
    return night.app.supervisor.session_state


def test_disarm_returns_an_established_session_to_disarmed_and_arm_works_again():
    night = imaging_night()
    assert night.gate.disarm() is True
    assert state(night) is SessionState.DISARMED
    night.cycles(6)
    assert state(night) is SessionState.DISARMED
    assert night.gate.refusal_reason() is None
    assert night.gate.arm()
    night.cycles(16)
    assert state(night) is SessionState.IMAGING_PERMITTED


def test_a_restart_after_disarm_is_not_treated_as_a_restart_while_armed():
    night = imaging_night()
    night.gate.disarm()
    night.cycles(6)
    restarted = GuardianV1Application(configured_capabilities=set(),
                                      recovery_store=GuardianV1RecoveryStore(night.folder / "recovery.json"))
    assert restarted.supervisor.recovery_blocked is False
    assert restarted.supervisor.restart_abort_pending is False


def test_disarm_never_switches_power():
    night = imaging_night()
    before = strip(night)
    night.gate.disarm()
    night.cycles(6)
    assert strip(night) == before


def test_after_disarm_a_closing_roof_no_longer_cuts_because_nothing_is_armed():
    night = imaging_night()
    night.gate.disarm()
    before = strip(night)
    night.rig.set_roof("CLOSED")
    night.cycles(20)
    assert state(night) is SessionState.DISARMED and night.app.supervisor.incident is None
    assert strip(night) == before


def test_disarm_never_clears_or_releases_an_open_incident():
    night = imaging_night()
    night.rig.set_roof("CLOSED")
    night.cycles(16)
    assert state(night) is SessionState.ABORTED
    assert night.gate.disarm() is False
    assert state(night) is SessionState.ABORTED
    assert night.app.supervisor.incident is not None
    assert night.app.supervisor.abort_acknowledged is False
    assert night.gate.refusal_reason()


def test_disarm_when_nothing_is_armed_changes_nothing():
    night = Night(None)
    night.cycles(3)
    assert night.gate.disarm() is False
    assert state(night) is SessionState.DISARMED


def test_a_failed_save_leaves_the_session_as_it_was_but_still_disarms_and_blocks_arm():
    night = imaging_night()
    store = night.app.recovery_store
    original = store.write

    def broken(_state):
        raise RecoveryStateError("disk full")

    store.write = broken
    try:
        assert night.gate.disarm() is False                      # must not raise
    finally:
        store.write = original
    assert night.gate.armed is False
    assert state(night) is SessionState.IMAGING_PERMITTED       # not changed without a durable record
    assert night.app.supervisor.recovery_blocked is True        # ARM stays blocked
    assert night.gate.refusal_reason()


def test_disarm_still_revokes_arm_when_the_application_cannot_end_a_session():
    gate = GuardianV1ArmedGate.__new__(GuardianV1ArmedGate)
    gate._armed = True
    gate.application = SimpleNamespace()                         # no end_session at all
    assert gate.disarm() is False
    assert gate.armed is False


def test_supervisor_end_session_only_acts_on_an_established_session_with_no_incident():
    supervisor = RuntimeSupervisor()
    assert supervisor.end_session() is False                     # DISARMED already
    supervisor._session_state = SessionState.IMAGING_PERMITTED
    assert supervisor.end_session() is True
    assert supervisor.session_state is SessionState.DISARMED
    supervisor._session_state = SessionState.WAITING_FOR_ROOF
    assert supervisor.end_session() is False                     # earlier states follow the armed flag


def test_the_operator_socket_reports_whether_the_session_ended():
    night = imaging_night()
    sock = night.runner.socket
    reply = sock._handle_arm_command({"command": "DISARM", "confirmed": True})
    assert reply["ok"] is True and reply["code"] == "DISARMED"
    assert "session ended" in reply["message"]
    again = sock._handle_arm_command({"command": "DISARM", "confirmed": True})
    assert again["ok"] is True and "session ended" not in again["message"]


def test_end_session_refuses_whenever_an_incident_exists_even_in_an_inconsistent_state():
    supervisor = RuntimeSupervisor()
    supervisor._session_state = SessionState.IMAGING_PERMITTED
    supervisor._incident = object()                              # belt and braces: never end a session over an incident
    assert supervisor.end_session() is False
    assert supervisor.session_state is SessionState.IMAGING_PERMITTED
