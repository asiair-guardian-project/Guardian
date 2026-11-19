import modules.guardian as guardian_module
from modules.guardian import Guardian
from modules.wave_monitor import WaveMonitorError


asiair_states = [False, True]
wave_states = ["OFFLINE", "ONLINE"]


def fake_asiair_available(*args, **kwargs):
    return asiair_states.pop(0)


def fake_read_wave_status():
    state = wave_states.pop(0)

    if state == "OFFLINE":
        raise WaveMonitorError("Simulated Wave powered off")

    return {
        "reachable": True,
        "axis1": {
            "status": "=TEST1",
            "position": "=AAAAAA",
        },
        "axis2": {
            "status": "=TEST2",
            "position": "=BBBBBB",
        },
    }


guardian_module.internet_available = lambda *args, **kwargs: True
guardian_module.asiair_available = fake_asiair_available
guardian_module.read_wave_status = fake_read_wave_status
guardian_module.ensure_wave_connection = (
    lambda *args, **kwargs: "OFFLINE"
)

guardian_module.read_alpaca_safety_status = lambda *args, **kwargs: {
    "status": "OPEN"
}

guardian_module.read_ups_status = lambda: {
    "power_source": "AC",
    "battery_percent": 100,
    "state": "TEST",
    "runtime": "TEST",
}


def main():
    print("Testing normal evening startup sequence")
    print()

    guardian = Guardian()
    guardian.config["roof"]["source"] = "alpaca"

    protection_calls = []

    guardian.evaluate_protection = (
        lambda source, event_type:
        protection_calls.append((source, event_type))
    )

    guardian.start_session()

    guardian.monitor_once()

    assert (
        guardian.session.state
        == guardian.session.IMAGING_PERMITTED
    )
    assert guardian.asiair_seen_online_this_session is False
    assert protection_calls == []

    print(
        "PASS: roof may open while ASIAIR and Wave are still off"
    )

    guardian.monitor_once()

    assert guardian.asiair_seen_online_this_session is True
    assert guardian.wave_status is not None
    assert protection_calls == []

    print(
        "PASS: ASIAIR and Wave may power up normally after roof opening"
    )

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
