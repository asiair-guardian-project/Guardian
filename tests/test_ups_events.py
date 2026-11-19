from modules.config_loader import load_config
from modules.event_engine import EventEngine
from modules.notification import NotificationEngine
from modules.state_tracker import StateTracker
from modules.ups_monitor import read_ups_status


config = load_config()

notifier = NotificationEngine(
    enabled=config["notifications"]["enabled"],
    minimum_level=config["notifications"]["minimum_level"],
)

events = EventEngine(notifier)
tracker = StateTracker()

status = read_ups_status()

power_source = status["power_source"]

if tracker.update(power_source):
    if power_source == "AC":
        events.emit(
            source="UPS",
            event_type="AC_POWER",
            severity="INFO",
            message=(
                f"Utility power available. "
                f"UPS battery {status['battery_percent']}%. "
                f"State: {status['state']}."
            ),
        )

    elif power_source == "UPS":
        events.emit(
            source="UPS",
            event_type="ON_BATTERY",
            severity="WARNING",
            message=(
                f"Utility power lost. "
                f"UPS battery {status['battery_percent']}%. "
                f"Runtime: {status['runtime']}."
            ),
        )

    else:
        events.emit(
            source="UPS",
            event_type="UNKNOWN",
            severity="ERROR",
            message="Unable to determine UPS power source.",
        )