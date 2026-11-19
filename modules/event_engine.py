from modules import logger


class EventEngine:
    """Handles Guardian events consistently."""

    def __init__(self, notifier):
        self.notifier = notifier

    def emit(self, source, event_type, severity, message):
        """
        Emit a Guardian event.

        severity must be one of:
        INFO, WARNING, ERROR, CRITICAL
        """

        severity = severity.upper()

        formatted_message = (
            f"{source} | {event_type} | {message}"
        )

        if severity == "INFO":
            logger.info(formatted_message)
            self.notifier.info(formatted_message)

        elif severity == "WARNING":
            logger.warning(formatted_message)
            self.notifier.warning(formatted_message)

        elif severity == "ERROR":
            logger.error(formatted_message)
            self.notifier.error(formatted_message)

        elif severity == "CRITICAL":
            logger.critical(formatted_message)
            self.notifier.critical(formatted_message)

        else:
            raise ValueError(
                f"Unsupported event severity: {severity}"
            )