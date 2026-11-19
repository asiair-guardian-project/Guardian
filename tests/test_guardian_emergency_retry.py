import time

from modules.guardian import Guardian
from modules.session_manager import SessionManager


class FakeGuardian(Guardian):
    def __init__(self):
        self.session = SessionManager(
            observatory_name="Test Observatory",
            guardian_version="0.6",
        )
        self.emergency_operator_acknowledged = False
        self.emergency_retry_active = False
        self.emergency_started_at = None
        self.emergency_last_attempt_at = None
        self.emergency_last_wave_stop_attempt_at = None
        self.emergency_source = None
        self.emergency_event_type = None
        self.protection_results = {}
        self.kasa_results = []
        self.kasa_calls = 0
        self.wave_stop_status = "NOT_REQUESTED"
        self.wave_stop_calls = 0

    def execute_wave_stop(self):
        self.wave_stop_calls += 1
        self.wave_stop_status = "VERIFIED"
        return True

    def execute_kasa_emergency_batch(self, targets):
        self.kasa_calls += 1
        return self.kasa_results.pop(0)


def successful_batch():
    return {
        "verification": {
            "Wave 150i": {"verified_off": True},
            "Pegasus": {"verified_off": True},
            "ASIAIR": {"verified_off": True},
        }
    }


def test_retry_intervals():
    guardian = FakeGuardian()
    now = time.monotonic()

    guardian.emergency_retry_active = True

    guardian.emergency_started_at = now - 30
    assert guardian.emergency_retry_interval_seconds() == 15

    guardian.emergency_started_at = now - 180
    assert guardian.emergency_retry_interval_seconds() == 60

    guardian.emergency_started_at = now - 900
    assert guardian.emergency_retry_interval_seconds() == 300

    print("PASS: emergency retry intervals are 15/60/300 seconds")


def test_retry_failure_then_success():
    guardian = FakeGuardian()

    guardian.start_emergency_retry(
        source="ASIAIR",
        event_type="OFFLINE",
    )

    guardian.kasa_results = [
        False,
        successful_batch(),
    ]

    guardian.emergency_last_attempt_at = (
        time.monotonic() - 20
    )

    result = guardian.process_emergency_retry()

    assert result is False
    assert guardian.emergency_retry_active is True
    assert guardian.kasa_calls == 1

    guardian.emergency_last_attempt_at = (
        time.monotonic() - 20
    )

    result = guardian.process_emergency_retry()

    assert result is True
    assert guardian.emergency_retry_active is False
    assert guardian.kasa_calls == 2

    assert guardian.protection_results[
        "POWER_OFF_WAVE"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_PEGASUS"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_ASIAIR"
    ] == "VERIFIED"

    print(
        "PASS: failed emergency shutdown remains pending "
        "and later verified shutdown clears retry state"
    )




def test_wave_stop_retries_until_verified():
    guardian = FakeGuardian()

    guardian.start_emergency_retry(
        source="ASIAIR",
        event_type="OFFLINE",
    )

    guardian.wave_stop_status = "FAILED"
    guardian.emergency_last_wave_stop_attempt_at = (
        time.monotonic() - 20
    )

    guardian.kasa_results = [False]

    result = guardian.process_emergency_retry()

    assert result is False
    assert guardian.wave_stop_calls == 1
    assert guardian.wave_stop_status == "VERIFIED"

    guardian.emergency_last_wave_stop_attempt_at = (
        time.monotonic() - 20
    )
    guardian.emergency_last_attempt_at = time.monotonic()

    guardian.process_emergency_retry()

    assert guardian.wave_stop_calls == 1

    print(
        "PASS: failed Wave STOP retries after 15 seconds "
        "and stops retrying once verified"
    )


class FakeAbortedSession:
    ABORTED = "ABORTED"

    def __init__(self):
        self.state = self.ABORTED


class FakeAbortedGuardian(Guardian):
    def __init__(self):
        self.session = FakeAbortedSession()
        self.control_calls = 0
        self.retry_calls = 0
        self.publish_calls = 0

    def process_control_command(self):
        self.control_calls += 1

    def process_emergency_retry(self):
        self.retry_calls += 1

    def publish_status(self):
        self.publish_calls += 1


def test_aborted_session_still_processes_retry():
    guardian = FakeAbortedGuardian()

    guardian.monitor_once()

    assert guardian.control_calls == 1
    assert guardian.retry_calls == 1
    assert guardian.publish_calls == 1

    print(
        "PASS: ABORTED session processes emergency retry "
        "and publishes status before normal monitoring returns"
    )


def main():
    print("Testing Guardian emergency retry logic")
    print()

    test_retry_intervals()
    test_retry_failure_then_success()
    test_wave_stop_retries_until_verified()
    test_aborted_session_still_processes_retry()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
