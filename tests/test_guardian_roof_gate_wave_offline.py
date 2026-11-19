import modules.guardian as guardian_module
from modules.guardian import Guardian
from modules.wave_monitor import WaveMonitorError


# Keep this test independent of real hardware/services.
guardian_module.internet_available = lambda *args, **kwargs: True
guardian_module.asiair_available = lambda *args, **kwargs: True

def failed_wave_read():
    raise WaveMonitorError("Simulated Wave offline")


guardian_module.read_wave_status = failed_wave_read

guardian_module.ensure_wave_connection = lambda *args, **kwargs: "OFFLINE"

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
    print("Testing Guardian roof gate with Wave offline")
    print()

    guardian = Guardian()
    guardian.config["roof"]["source"] = "alpaca"

    guardian.start_session()
    guardian.monitor_once()

    assert (
        guardian.session.state
        == guardian.session.IMAGING_PERMITTED
    )

    print(
        "PASS: fresh OPEN roof permits imaging "
        "even when Wave control link is offline"
    )
    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
