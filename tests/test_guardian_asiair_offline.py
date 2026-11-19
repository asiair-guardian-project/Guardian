from unittest.mock import patch

from modules.guardian import Guardian

class FakeEventEngine:
    def __init__(self):
        self.events = []

    def emit(self, **kwargs):
        self.events.append(kwargs)


class FakeAlertManager:
    def __init__(self):
        self.alerts = []

    def set_alert(
        self,
        severity,
        source,
        event_type,
        message,
        protection_results=None,
    ):
        alert = {
            "severity": severity,
            "source": source,
            "event_type": event_type,
            "message": message,
            "protection_results": protection_results or {},
        }

        self.alerts.append(alert)
        return alert

class FakeSession:
    def __init__(self, active=True):
        self.active = active
        self.aborted = False

    def abort(self):
        if not self.active:
            return False
        self.active = False
        self.aborted = True
        return True


class FakeGuardian(Guardian):
    def __init__(self):
        self.session = FakeSession(active=True)
        self.protection_calls = []
        self.alert_manager = FakeAlertManager()
        self.events = FakeEventEngine()
        self.protection_results = {
            "STOP_WAVE": "VERIFIED",
            "POWER_OFF_PEGASUS": "VERIFIED",
            "POWER_OFF_ASIAIR": "VERIFIED",
        }

    def evaluate_protection(self, source, event_type):
        self.protection_calls.append(
            (source, event_type)
        )


def test_stationary_wave():
    guardian = FakeGuardian()

    fake_sample = {
        "axis1": {"delta": 0},
        "axis2": {"delta": 0},
    }

    with patch(
        "modules.guardian.sample_positions",
        return_value=fake_sample,
    ):
        with patch(
            "modules.guardian.wave_is_moving",
            return_value=False,
        ):
            result = guardian.handle_asiair_offline()

    assert result is False
    assert guardian.protection_calls == []
    assert guardian.alert_manager.alerts == []

    print(
        "PASS: stationary Wave marks normal shutdown "
        "and does not trigger protection"
    )


def test_moving_wave():
    guardian = FakeGuardian()

    fake_sample = {
        "axis1": {"delta": 12},
        "axis2": {"delta": 0},
    }

    with patch(
        "modules.guardian.sample_positions",
        return_value=fake_sample,
    ):
        with patch(
            "modules.guardian.wave_is_moving",
            return_value=True,
        ):
            result = guardian.handle_asiair_offline()

    assert result is True
    assert guardian.session.aborted is True
    assert guardian.protection_calls == [
        ("ASIAIR", "OFFLINE")
    ]
    assert len(guardian.alert_manager.alerts) == 1

    alert = guardian.alert_manager.alerts[0]

    assert alert["source"] == "ASIAIR"
    assert alert["event_type"] == "OFFLINE_WAVE_MOVING"
    assert alert["severity"] == "CRITICAL"

    print("PASS: moving Wave triggers protection")


def test_wave_motion_unknown():
    guardian = FakeGuardian()

    from modules.wave_position_sampler import (
        WavePositionSamplerError,
    )

    with patch(
        "modules.guardian.sample_positions",
        side_effect=WavePositionSamplerError(
            "simulated read failure"
        ),
    ):
        result = guardian.handle_asiair_offline()

    assert result is True
    assert guardian.session.aborted is True
    assert guardian.protection_calls == [
        ("ASIAIR", "OFFLINE")
    ]
    assert len(guardian.alert_manager.alerts) == 1

    alert = guardian.alert_manager.alerts[0]

    assert alert["source"] == "ASIAIR"
    assert alert["event_type"] == "OFFLINE_WAVE_MOTION_UNKNOWN"
    assert alert["severity"] == "CRITICAL"

    print("PASS: unknown Wave motion fails safe")


def main():
    print("Testing Guardian ASIAIR offline handling")
    print()

    test_stationary_wave()
    test_moving_wave()
    test_wave_motion_unknown()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()