from modules.config_loader import load_config
from modules.notification import NotificationEngine


config = load_config()
settings = config["notifications"]

notifier = NotificationEngine(
    enabled=settings["enabled"],
    minimum_level=settings["minimum_level"],
)

notifier.info("Guardian notification test started")
notifier.warning("This is a warning notification")
notifier.error("This is an error notification")
notifier.critical("This is a critical notification")