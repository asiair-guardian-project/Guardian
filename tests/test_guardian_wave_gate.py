from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from modules.guardian import Guardian
from modules.wave_monitor import WaveMonitorError


test_file = Path("tests/test_wave_gate_roof_status.txt")


def write_roof(status):
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %I:%M:%S%p CST"
    )

    test_file.write_text(
        f"{timestamp} Roof Status: {status}\n",
        encoding="utf-8",
    )


def main():
    print("Testing Guardian roof gate with Wave offline")
    print()

    guardian = Guardian()

    guardian.config["roof"]["source"] = "file"
    guardian.config["roof"]["status_file"] = str(test_file)
    guardian.config["roof"]["stale_after_seconds"] = 300

    guardian.start_session()
    write_roof("OPEN")

    with patch(
        "modules.guardian.internet_available",
        return_value=True,
    ), patch(
        "modules.guardian.asiair_available",
        return_value=True,
    ), patch(
        "modules.guardian.read_wave_status",
        side_effect=WaveMonitorError(
            "Simulated Wave communication failure."
        ),
    ), patch(
        "modules.guardian.ensure_wave_connection",
        return_value="OFFLINE",
    ), patch(
        "modules.guardian.read_ups_status",
        return_value={
            "power_source": "AC",
            "battery_percent": 100,
            "state": "TEST",
            "runtime": "TEST",
        },
    ):
        guardian.monitor_once()

    assert guardian.session.state == guardian.session.IMAGING_PERMITTED
    assert guardian.session.imaging_permitted is True

    print(
        "PASS: fresh OPEN roof permits imaging "
        "when Wave is offline"
    )
    print()
    print("RESULT: PASS")

    if test_file.exists():
        test_file.unlink()


if __name__ == "__main__":
    main()
