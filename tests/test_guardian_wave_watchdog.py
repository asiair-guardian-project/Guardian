from unittest.mock import patch

from modules.guardian import Guardian
from modules.wave_monitor import WaveMonitorError


class FakeSession:
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
    def __init__(self):
        self.events = []

    def emit(self, **kwargs):
        self.events.append(kwargs)


class FakeState:
    def __init__(self, initial_state=None):
        self._state = initial_state

    @property
    def state(self):
        return self._state

    def update(self, value):
        if self._state == value:
            return False

        self._state = value
        return True


class FakeGuardian(Guardian):
    def __init__(self):
        self.session = FakeSession()
        self.events = FakeEvents()
        self.network_state = FakeState()
        self.asiair_state = FakeState()
        self.wave_seen_online_this_session = False
        self.wave_state = FakeState()
        self.wave_status = None
        self.protection_calls = []
        self.config = {
            "network": {
                "internet_test_url": "unused",
                "timeout_seconds": 1,
            },
            "asiair": {
                "ip_address": "unused",
                "timeout_seconds": 1,
            },
        }

    def process_control_command(self):
        pass

    def evaluate_protection(self, source, event_type):
        self.protection_calls.append((source, event_type))
        return []


def test_recovery_success():
    guardian = FakeGuardian()
    guardian.wave_seen_online_this_session = True

    recovered_status = {
        "axis1": {
            "status": "=A",
            "position": "=000080",
        },
        "axis2": {
            "status": "=A",
            "position": "=000080",
        },
    }

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        side_effect=[
            WaveMonitorError("simulated initial failure"),
            recovered_status,
        ],
    ), patch(
        "modules.guardian.ensure_wave_connection",
        return_value="RECOVERED",
    ):
        # Stop the test immediately after the Wave section.
        with patch.object(
            guardian.wave_state,
            "update",
            side_effect=RuntimeError("STOP_AFTER_WAVE"),
        ):
            try:
                guardian.monitor_once()
            except RuntimeError as error:
                assert str(error) == "STOP_AFTER_WAVE"

    assert guardian.wave_status == recovered_status
    assert guardian.protection_calls == []
    assert guardian.session.state == guardian.session.IMAGING_PERMITTED

    print(
        "PASS: recovered Wave link is re-read and "
        "session remains active"
    )


def test_recovery_failure():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        side_effect=WaveMonitorError(
            "simulated Wave communication failure"
        ),
    ), patch(
        "modules.guardian.ensure_wave_connection",
        return_value="OFFLINE",
    ):
        with patch.object(
            guardian.wave_state,
            "update",
            side_effect=RuntimeError("STOP_AFTER_WAVE"),
        ):
            try:
                guardian.monitor_once()
            except RuntimeError as error:
                assert str(error) == "STOP_AFTER_WAVE"

    assert guardian.protection_calls == []
    assert guardian.session.state == guardian.session.IMAGING_PERMITTED
    assert guardian.session.active is True

    print(
        "PASS: persistent Wave link loss enters degraded mode "
        "without aborting the session"
    )



def test_loss_after_online_warns():
    guardian = FakeGuardian()
    guardian.wave_seen_online_this_session = True

    guardian.wave_state.update = lambda value: True

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        side_effect=WaveMonitorError(
            "simulated Wave loss after prior connection"
        ),
    ), patch(
        "modules.guardian.ensure_wave_connection",
        return_value="OFFLINE",
    ):
        try:
            guardian.monitor_once()
        except KeyError:
            pass

    wave_offline_events = [
        event
        for event in guardian.events.events
        if event.get("source") == "WAVE"
        and event.get("event_type") == "OFFLINE"
        and event.get("severity") == "WARNING"
    ]

    assert wave_offline_events

    print(
        "PASS: Wave loss after prior connection still emits WARNING"
    )

def main():
    print("Testing Guardian Wave control-link watchdog")
    print()

    test_recovery_success()
    test_recovery_failure()
    test_loss_after_online_warns()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
