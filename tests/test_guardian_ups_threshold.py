from unittest.mock import patch
from modules.guardian import Guardian

class FakeState:
    def update(self, value):
        return False

class FakeSession:
    WAITING_FOR_ROOF = "WAITING_FOR_ROOF"
    IMAGING_PERMITTED = "IMAGING_PERMITTED"
    ABORTED = "ABORTED"

    def __init__(self):
        self.state = self.IMAGING_PERMITTED

    @property
    def active(self):
        return self.state == self.IMAGING_PERMITTED

    def abort(self):
        if not self.active:
            return False
        self.state = self.ABORTED
        return True

class FakeEvents:
    def emit(self, **kwargs):
        pass

class FakeGuardian(Guardian):
    def __init__(self):
        self.session = FakeSession()
        self.events = FakeEvents()
        self.network_state = FakeState()
        self.asiair_state = FakeState()
        self.wave_state = FakeState()
        self.roof_state = FakeState()
        self.roof_freshness_state = FakeState()
        self.ups_state = FakeState()
        self.protection_results = {}
        self.wave_status = None
        self.config = {
            "network": {"internet_test_url": "unused", "timeout_seconds": 1},
            "asiair": {"ip_address": "unused", "timeout_seconds": 1},
            "roof": {"source": "alpaca", "alpaca_host": "unused", "alpaca_device_number": 17},
        }

    def process_control_command(self):
        pass

    def publish_status(self):
        pass

def test_low_battery_verified_shutdown():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        return_value={
            "axis1": {"status": "=A", "position": "=000080"},
            "axis2": {"status": "=A", "position": "=000080"},
        },
    ), patch(
        "modules.guardian.read_alpaca_safety_status",
        return_value={"status": "OPEN"},
    ), patch(
        "modules.guardian.read_ups_status",
        return_value={
            "power_source": "UPS",
            "battery_percent": 35,
            "state": "DISCHARGING",
            "runtime": "00:20",
        },
    ):
        guardian.evaluate_protection = lambda source, event_type: (
            guardian.protection_results.update({
                "POWER_OFF_WAVE": "VERIFIED",
                "POWER_OFF_PEGASUS": "VERIFIED",
                "POWER_OFF_ASIAIR": "VERIFIED",
            })
        )

        guardian.monitor_once()

    assert guardian.session.state == guardian.session.ABORTED
    print("PASS: verified low-battery shutdown aborts session")



def test_low_battery_failed_shutdown_stays_active():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        return_value={
            "axis1": {"status": "=A", "position": "=000080"},
            "axis2": {"status": "=A", "position": "=000080"},
        },
    ), patch(
        "modules.guardian.read_alpaca_safety_status",
        return_value={"status": "OPEN"},
    ), patch(
        "modules.guardian.read_ups_status",
        return_value={
            "power_source": "UPS",
            "battery_percent": 35,
            "state": "DISCHARGING",
            "runtime": "00:20",
        },
    ):
        guardian.evaluate_protection = lambda source, event_type: (
            guardian.protection_results.update({
                "POWER_OFF_WAVE": "VERIFIED",
                "POWER_OFF_PEGASUS": "FAILED",
                "POWER_OFF_ASIAIR": "VERIFIED",
            })
        )

        guardian.monitor_once()

    # Low UPS battery must abort imaging even if shutdown fails.
    # This test mocks evaluate_protection, so it does not test retries.
    assert guardian.session.active is False
    assert guardian.session.state == guardian.session.ABORTED
    assert guardian.protection_results["POWER_OFF_PEGASUS"] == "FAILED"
    print("PASS: failed low-battery shutdown still aborts imaging")
if __name__ == "__main__":
    test_low_battery_verified_shutdown()
    test_low_battery_failed_shutdown_stays_active()


def test_low_battery_failed_shutdown_activates_retry():
    """Low UPS battery aborts imaging and preserves failed shutdown retries."""
    import time

    guardian = FakeGuardian()

    # Initialize emergency-retry state omitted by the test double.
    guardian.emergency_operator_acknowledged = False
    guardian.emergency_retry_active = False
    guardian.emergency_started_at = None
    guardian.emergency_last_attempt_at = None
    guardian.emergency_last_wave_stop_attempt_at = None
    guardian.emergency_source = None
    guardian.emergency_event_type = None
    guardian.wave_stop_status = "NOT_REQUESTED"

    # Simulate a failed Pegasus shutdown without touching hardware.
    def simulated_protection(source, event_type):
        guardian.protection_results.update({
            "POWER_OFF_WAVE": "VERIFIED",
            "POWER_OFF_PEGASUS": "FAILED",
            "POWER_OFF_ASIAIR": "VERIFIED",
        })
        guardian.start_emergency_retry(source, event_type)

    guardian.evaluate_protection = simulated_protection

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        return_value={
            "axis1": {"status": "=A", "position": "=000080"},
            "axis2": {"status": "=A", "position": "=000080"},
        },
    ), patch(
        "modules.guardian.read_alpaca_safety_status",
        return_value={"status": "OPEN"},
    ), patch(
        "modules.guardian.read_ups_status",
        return_value={
            "power_source": "UPS",
            "battery_percent": 35,
            "state": "DISCHARGING",
            "runtime": "00:20",
        },
    ):
        guardian.monitor_once()

    assert guardian.session.state == guardian.session.ABORTED
    assert guardian.session.active is False
    assert guardian.emergency_retry_active is True
    assert guardian.emergency_source == "UPS"
    assert guardian.emergency_event_type == "LOW_BATTERY"
    assert guardian.protection_results["POWER_OFF_PEGASUS"] == "FAILED"

    # Verify retry scheduling survives the session abort.
    guardian.emergency_last_attempt_at = time.monotonic() - 20
    assert guardian.emergency_retry_due() is True

    # Simulate successful verification on the next retry.
    guardian.execute_kasa_emergency_batch = lambda targets: {
        "verification": {
            "Wave 150i": {"verified_off": True},
            "Pegasus": {"verified_off": True},
            "ASIAIR": {"verified_off": True},
        }
    }
    guardian.quit_asiair_app = lambda: None

    assert guardian.process_emergency_retry() is True
    assert guardian.emergency_retry_active is False
    assert guardian.session.state == guardian.session.ABORTED
    assert guardian.protection_results["POWER_OFF_PEGASUS"] == "VERIFIED"
