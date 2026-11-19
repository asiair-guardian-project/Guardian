import modules.guardian as guardian_module
from modules.guardian import Guardian


asiair_states = [False, True, False]


def fake_asiair_available(*args, **kwargs):
    return asiair_states.pop(0)


guardian_module.internet_available = lambda *args, **kwargs: True
guardian_module.asiair_available = fake_asiair_available

guardian_module.read_wave_status = lambda: {
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
    print("Testing ASIAIR per-session online history")
    print()

    guardian = Guardian()
    guardian.config["roof"]["source"] = "alpaca"

    offline_calls = []

    def fake_handle_asiair_offline():
        offline_calls.append(True)
        return True

    guardian.handle_asiair_offline = fake_handle_asiair_offline

    guardian.start_session()

    guardian.monitor_once()

    assert guardian.asiair_seen_online_this_session is False
    assert offline_calls == []
    assert (
        guardian.session.state
        == guardian.session.IMAGING_PERMITTED
    )

    print(
        "PASS: ASIAIR may be offline before first startup "
        "without triggering controller-loss protection"
    )

    guardian.monitor_once()

    assert guardian.asiair_seen_online_this_session is True
    assert offline_calls == []

    print(
        "PASS: ASIAIR online state arms controller-loss protection"
    )

    guardian.monitor_once()

    assert offline_calls == [True]

    print(
        "PASS: later ASIAIR loss invokes existing offline handler"
    )

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
