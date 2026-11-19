from pathlib import Path
from modules.guardian import Guardian
from modules.session_manager import SessionManager
from modules.emergency_state_store import EmergencyStateStore
import tempfile


class FakeEvents:
    def emit(self, **kwargs):
        pass


class FakeGuardian(Guardian):
    def __init__(self):
        self.session = SessionManager(
            observatory_name="Test Observatory",
            guardian_version="0.6",
        )
        self.events = FakeEvents()
        self.emergency_retry_active = False
        self.roof_close_protection_triggered = False
        self.asiair_seen_online_this_session = False
        self.wave_seen_online_this_session = False
        self.wave_stop_status = "NOT_REQUESTED"
        self.protection_results = {}
        self.emergency_operator_acknowledged = False
        self.roof_ready_for_rearm_result = True

        # Isolated test-only persistent emergency state.
        self._test_directory = tempfile.TemporaryDirectory()
        self.emergency_state_store = EmergencyStateStore(
            Path(self._test_directory.name) / "emergency_state.json"
        )
        self.emergency_state_store.write({
            "schema_version": 1,
            "session_state": "DISARMED",
            "abort_reason": None,
            "operator_acknowledged": False,
            "emergency_retry_active": False,
            "protection_results": {},
        })
        assert self.restore_emergency_state()

    def persist_test_abort(self):
        """Persist a simulated abort in this test's isolated state file."""
        record = self.emergency_state_store.read()
        record.update({
            "session_state": "ABORTED",
            "abort_reason": "SIMULATED_TEST_EMERGENCY",
            "operator_acknowledged": False,
            "emergency_retry_active": self.emergency_retry_active,
            "protection_results": dict(self.protection_results),
        })
        self.emergency_state_store.write(record)

    def roof_ready_for_rearm(self):
        """Simulate roof verification without network or hardware access."""
        return self.roof_ready_for_rearm_result


def test_unresolved_emergency_blocks_new_session():
    guardian = FakeGuardian()

    assert guardian.start_session() is True
    assert guardian.session.abort() is True
    guardian.persist_test_abort()
    assert guardian.session.state == guardian.session.ABORTED

    guardian.emergency_retry_active = True

    assert guardian.start_session() is False
    assert guardian.session.state == guardian.session.ABORTED


def test_ack_abort_cancels_retries_without_rearming():
    guardian = FakeGuardian()
    assert guardian.start_session() is True
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    guardian.emergency_retry_active = True
    guardian.wave_stop_status = "FAILED"
    guardian.protection_results = {
        "POWER_OFF_WAVE": "FAILED",
        "POWER_OFF_ASIAIR": "FAILED",
    }

    assert guardian.acknowledge_emergency_abort() is True
    assert guardian.emergency_retry_active is False
    assert guardian.emergency_operator_acknowledged is True
    assert guardian.session.state == guardian.session.ABORTED
    assert guardian.wave_stop_status == "FAILED"
    assert guardian.protection_results["POWER_OFF_WAVE"] == "FAILED"
    assert guardian.protection_results["POWER_OFF_ASIAIR"] == "FAILED"
    assert guardian.emergency_wave_stop_retry_due() is False
    assert guardian.emergency_retry_due() is False


def test_ack_abort_rejected_without_aborted_session():
    guardian = FakeGuardian()
    guardian.emergency_retry_active = True

    assert guardian.acknowledge_emergency_abort() is False
    assert guardian.emergency_retry_active is True


def test_acknowledged_abort_cannot_restart_emergency():
    guardian = FakeGuardian()

    assert guardian.start_session() is True
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    guardian.emergency_retry_active = True
    assert guardian.acknowledge_emergency_abort() is True

    guardian.start_emergency_retry(
        source="ROOF",
        event_type="CLOSED_WAVE_MOVING",
    )

    assert guardian.emergency_retry_active is False
    assert guardian.emergency_operator_acknowledged is True
    assert guardian.session.state == guardian.session.ABORTED


def test_new_session_after_acknowledged_abort():
    guardian = FakeGuardian()

    # First imaging session encounters an emergency.
    assert guardian.start_session() is True
    guardian.start_emergency_retry(
        source="ROOF",
        event_type="CLOSED_WAVE_MOVING",
    )
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    # Old emergency prevents premature rearming.
    assert guardian.start_session() is False

    # Operator explicitly terminates outstanding retries.
    assert guardian.acknowledge_emergency_abort() is True
    assert guardian.emergency_retry_active is False

    # Operator deliberately arms a new session.
    assert guardian.start_session() is True
    assert guardian.emergency_retry_active is False
    assert guardian.emergency_operator_acknowledged is False
    assert guardian.emergency_source is None
    assert guardian.emergency_event_type is None
    assert guardian.wave_stop_status == "NOT_REQUESTED"
    assert guardian.protection_results == {}

    # A genuinely new emergency must still activate protection.
    guardian.start_emergency_retry(
        source="ROOF",
        event_type="CLOSED_WAVE_MOVING",
    )
    assert guardian.emergency_retry_active is True
    assert guardian.emergency_operator_acknowledged is False


def test_ack_abort_control_command(tmp_path):
    guardian = FakeGuardian()

    assert guardian.start_session() is True
    guardian.start_emergency_retry(
        source="ROOF",
        event_type="CLOSED_WAVE_MOVING",
    )
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    command_file = tmp_path / "guardian_command.txt"
    guardian.config = {
        "control": {"command_file": str(command_file)}
    }

    command_file.write_text("ACK_ABORT")
    guardian.process_control_command()

    assert guardian.emergency_retry_active is False
    assert guardian.emergency_operator_acknowledged is True
    assert guardian.session.state == guardian.session.ABORTED
    assert command_file.read_text() == ""


def test_status_distinguishes_acknowledgment_from_shutdown(tmp_path):
    import json

    guardian = FakeGuardian()
    assert guardian.start_session() is True
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    guardian.emergency_retry_active = True
    guardian.protection_results = {
        "POWER_OFF_WAVE": "FAILED",
        "POWER_OFF_PEGASUS": "FAILED",
        "POWER_OFF_ASIAIR": "FAILED",
    }

    assert guardian.acknowledge_emergency_abort() is True

    status_file = tmp_path / "status.json"
    guardian.config = {
        "control": {"status_file": str(status_file)}
    }
    guardian.version = "0.6"
    guardian.wave_status = None

    guardian.publish_status()

    status = json.loads(status_file.read_text())

    assert status["session_state"] == "ABORTED"
    assert status["emergency_retry_active"] is False
    assert status["emergency_operator_acknowledged"] is True
    assert status["emergency_power_shutdown_verified"] is False


if __name__ == "__main__":
    test_unresolved_emergency_blocks_new_session()
    print("PASS: unresolved emergency blocks new session")


def test_verified_shutdown_still_requires_ack_abort():
    guardian = FakeGuardian()

    assert guardian.start_session() is True
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    guardian.protection_results = {
        "POWER_OFF_WAVE": "VERIFIED",
        "POWER_OFF_PEGASUS": "VERIFIED",
        "POWER_OFF_ASIAIR": "VERIFIED",
    }
    guardian.emergency_retry_active = False

    # Successful shutdown does not authorize a new session.
    assert guardian.start_session() is False
    assert guardian.session.state == guardian.session.ABORTED

    # Acknowledgment does not itself restart imaging.
    assert guardian.acknowledge_emergency_abort() is True
    assert guardian.session.state == guardian.session.ABORTED
    assert guardian.session.active is False

    # Explicit ARM is now allowed by the acknowledgment interlock.
    assert guardian.start_session() is True
    assert guardian.emergency_operator_acknowledged is False


def test_acknowledged_abort_requires_open_roof():
    guardian = FakeGuardian()

    assert guardian.start_session() is True
    assert guardian.session.abort() is True
    guardian.persist_test_abort()

    assert guardian.acknowledge_emergency_abort() is True

    # Simulate CLOSED, STALE, UNKNOWN, or an unreadable roof.
    guardian.roof_ready_for_rearm_result = False

    assert guardian.start_session() is False
    assert guardian.session.state == guardian.session.ABORTED
    assert guardian.emergency_operator_acknowledged is True

    # Once a fresh OPEN reading is available, explicit ARM succeeds.
    guardian.roof_ready_for_rearm_result = True

    assert guardian.start_session() is True
    assert guardian.emergency_operator_acknowledged is False
