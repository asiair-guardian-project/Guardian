from unittest.mock import patch

from modules.guardian import Guardian


def prepare_guardian():
    guardian = Guardian()

    guardian.config["network"]["internet_test_url"] = "https://example.invalid"
    guardian.config["roof"]["status_file"] = (
        "tests/current_roof_status.txt"
    )
    guardian.config["roof"]["stale_after_seconds"] = None

    return guardian


def test_ethernet_ip_is_used():
    guardian = prepare_guardian()

    guardian.config["asiair"]["ip_address"] = "192.168.1.127"

    calls = []

    def fake_asiair_available(host, timeout_seconds):
        calls.append((host, timeout_seconds))
        return True

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ):
        with patch(
            "modules.guardian.asiair_available",
            side_effect=fake_asiair_available,
        ):
            with patch(
                "modules.guardian.read_wave_status",
                return_value={
                    "reachable": True,
                    "axis1": {
                        "status": "=TEST1",
                        "position": "=AAAAAA",
                    },
                    "axis2": {
                        "status": "=TEST2",
                        "position": "=BBBBBB",
                    },
                },
            ):
                with patch(
                    "modules.guardian.read_ups_status",
                    return_value={
                        "power_source": "AC",
                        "battery_percent": 100,
                        "state": "TEST",
                        "runtime": "TEST",
                    },
                ):
                    guardian.monitor_once()

    assert calls == [
        ("192.168.1.127", 2)
    ]

    print(
        "PASS: Guardian uses the configured ASIAIR Ethernet IP"
    )


def test_blank_ip_does_not_fall_back_to_hostname():
    guardian = prepare_guardian()

    guardian.config["asiair"]["ip_address"] = ""
    guardian.config["asiair"]["hostname"] = "asiair.local"

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ):
        with patch(
            "modules.guardian.asiair_available"
        ) as asiair_mock:
            with patch(
                "modules.guardian.read_wave_status",
                return_value={
                    "reachable": True,
                    "axis1": {
                        "status": "=TEST1",
                        "position": "=AAAAAA",
                    },
                    "axis2": {
                        "status": "=TEST2",
                        "position": "=BBBBBB",
                    },
                },
            ):
                with patch(
                    "modules.guardian.read_ups_status",
                    return_value={
                        "power_source": "AC",
                        "battery_percent": 100,
                        "state": "TEST",
                        "runtime": "TEST",
                    },
                ):
                    guardian.monitor_once()

    asiair_mock.assert_not_called()

    print(
        "PASS: missing Ethernet IP does not fall back to ASIAIR hostname"
    )


def main():
    print("Testing Guardian ASIAIR Ethernet-only connectivity")
    print()

    test_ethernet_ip_is_used()
    test_blank_ip_does_not_fall_back_to_hostname()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
