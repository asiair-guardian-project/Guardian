from datetime import datetime
from pathlib import Path

import modules.guardian as guardian_module
from modules.guardian import Guardian


test_file = Path("tests/test_roof_sequence_status.txt")


def write_roof(status):
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %I:%M:%S%p CST"
    )

    test_file.write_text(
        f"{timestamp} Roof Status: {status}\n",
        encoding="utf-8",
    )


# Prevent this test from depending on real external hardware/services.
guardian_module.internet_available = lambda *args, **kwargs: True
guardian_module.asiair_available = lambda *args, **kwargs: True

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

guardian_module.read_ups_status = lambda: {
    "power_source": "AC",
    "battery_percent": 100,
    "state": "TEST",
    "runtime": "TEST",
}


guardian = Guardian()

# Force Guardian to use our temporary roof file.
guardian.config["roof"]["source"] = "file"
guardian.config["roof"]["status_file"] = str(test_file)
guardian.config["roof"]["stale_after_seconds"] = 300

# Record protection calls instead of executing hardware actions.
protection_calls = []


def fake_evaluate_protection(source, event_type):
    protection_calls.append(
        (source, event_type)
    )

    print(
        f"PROTECTION REQUESTED: "
        f"{source} | {event_type}"
    )

    return []


guardian.evaluate_protection = fake_evaluate_protection


print("Start session")
guardian.start_session()
print(f"State: {guardian.session.state}")
print()


print("STEP 1: Roof CLOSED + FRESH")
write_roof("CLOSED")
guardian.monitor_once()
print(f"State: {guardian.session.state}")
print(f"Protection calls: {protection_calls}")
print()


print("STEP 2: Roof OPEN + FRESH")
write_roof("OPEN")
guardian.monitor_once()
print(f"State: {guardian.session.state}")
print(f"Protection calls: {protection_calls}")
print()


print("STEP 3: Roof CLOSED + FRESH")
write_roof("CLOSED")
guardian.monitor_once()
print(f"State: {guardian.session.state}")
print(f"Protection calls: {protection_calls}")
print()


print("STEP 4: Roof remains CLOSED")
write_roof("CLOSED")
guardian.monitor_once()
print(f"State: {guardian.session.state}")
print(f"Protection calls: {protection_calls}")
print()


if test_file.exists():
    test_file.unlink()