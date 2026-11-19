from modules.config_loader import load_config
from modules.event_engine import EventEngine
from modules.notification import NotificationEngine


config = load_config()

notifier = NotificationEngine(
    enabled=config["notifications"]["enabled"],
    minimum_level=config["notifications"]["minimum_level"],
)

events = EventEngine(notifier)

events.emit(
    source="NETWORK",
    event_type="CONNECTED",
    severity="INFO",
    message="Internet connection is available.",
)

events.emit(
    source="ASIAIR",
    event_type="OFFLINE",
    severity="WARNING",
    message="ASIAIR is not responding.",
)

events.emit(
    source="MOUNT",
    event_type="POSITION_LOST",
    severity="CRITICAL",
    message="Mount position integrity has been lost.",
)