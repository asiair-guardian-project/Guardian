import json
from pathlib import Path

from modules.status_writer import write_status


test_file = Path("tests/guardian_status_test.json")

status_data = {
    "guardian_version": "0.6",
    "running": True,
    "session_active": False,
    "protection": "DISARMED",
    "pid": 1234,
}

write_status(
    test_file,
    status_data,
)

print(test_file.read_text(encoding="utf-8"))

loaded = json.loads(
    test_file.read_text(encoding="utf-8")
)

print(f"Guardian version: {loaded['guardian_version']}")
print(f"Running: {loaded['running']}")
print(f"Session active: {loaded['session_active']}")
print(f"Protection: {loaded['protection']}")
print(f"PID: {loaded['pid']}")

test_file.unlink()