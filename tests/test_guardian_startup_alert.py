from modules.guardian import Guardian


class FakeAlertManager:
    def __init__(self, alert):
        self.alert = alert

    def read_alert(self):
        return self.alert


class FakeNotifier:
    def __init__(self):
        self.notifications = []

    def mac_notification(self, title, message):
        self.notifications.append(
            {
                "title": title,
                "message": message,
            }
        )
        return True


class FakeGuardian(Guardian):
    def __init__(self, alert):
        self.alert_manager = FakeAlertManager(alert)
        self.notifier = FakeNotifier()


def test_active_alert():
    alert = {
        "active": True,
        "source": "ASIAIR",
        "event_type": "OFFLINE_WAVE_MOVING",
        "message": (
            "ASIAIR became unavailable while the Wave "
            "was moving. Guardian executed protection."
        ),
        "protection_results": {
            "STOP_WAVE": "VERIFIED",
            "POWER_OFF_WAVE": "VERIFIED",
            "POWER_OFF_PEGASUS": "VERIFIED",
            "POWER_OFF_ASIAIR": "VERIFIED",
        },
    }

    guardian = FakeGuardian(alert)

    result = guardian.show_startup_operator_alert()

    assert result is True
    assert len(guardian.notifier.notifications) == 1

    notification = guardian.notifier.notifications[0]

    assert notification["title"] == (
        "Guardian Overnight Incident"
    )

    assert (
        "ASIAIR became unavailable while the Wave was moving."
        in notification["message"]
    )

    assert (
        "Guardian executed protection."
        in notification["message"]
    )

    assert "STOP_WAVE: VERIFIED" in notification["message"]
    assert "POWER_OFF_WAVE: VERIFIED" in notification["message"]
    assert "POWER_OFF_PEGASUS: VERIFIED" in notification["message"]
    assert "POWER_OFF_ASIAIR: VERIFIED" in notification["message"]

    print(
        "PASS: active incident produces one startup notification "
        "with a concise incident summary and protection results"
    )


def test_no_alert():
    guardian = FakeGuardian(None)

    result = guardian.show_startup_operator_alert()

    assert result is False
    assert guardian.notifier.notifications == []

    print(
        "PASS: no active incident produces no startup notification"
    )


def main():
    print("Testing Guardian startup alert behavior")
    print()

    test_active_alert()
    test_no_alert()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()