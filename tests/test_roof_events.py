from pathlib import Path

from modules.config_loader import load_config
from modules.event_engine import EventEngine
from modules.notification import NotificationEngine
from modules.roof_monitor import read_roof_status
from modules.state_tracker import StateTracker


config = load_config()

notifier = NotificationEngine(
    enabled=config["notifications"]["enabled"],
    minimum_level=config["notifications"]["minimum_level"],
)

events = EventEngine(notifier)
tracker = StateTracker()

test_file = Path("tests/sample_roof_status.txt")

roof_lines = [
    "2026-08-07 07:06:59AM CST Roof Status: CLOSED\n",
    "2026-08-07 07:07:59AM CST Roof Status: CLOSED\n",
    "2026-08-07 07:08:59AM CST Roof Status: OPEN\n",
    "2026-08-07 07:09:59AM CST Roof Status: OPEN\n",
    "2026-08-07 07:10:59AM CST Roof Status: CLOSING\n",
    "2026-08-07 07:11:59AM CST Roof Status: CLOSED\n",
]

for line in roof_lines:
    test_file.write_text(line, encoding="utf-8")

    result = read_roof_status(test_file)
    status = result["status"]

    if tracker.update(status):
        events.emit(
            source="ROOF",
            event_type=status,
            severity="INFO",
            message=f"Roof status changed to {status}.",
        )

if test_file.exists():
    test_file.unlink()