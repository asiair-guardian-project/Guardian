import json
import urllib.parse
import urllib.request
import subprocess

from modules.keychain import KeychainError, get_secret


LEVEL_VALUES = {
    "INFO": 10,
    "WARNING": 20,
    "ERROR": 30,
    "CRITICAL": 40,
}


class NotificationEngine:
    """Routes Guardian notifications to external destinations."""

    PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

    def __init__(
        self,
        enabled=True,
        minimum_level="INFO",
        pushover_enabled=False,
    ):
        self.enabled = enabled
        self.minimum_level = minimum_level.upper()
        self.pushover_enabled = pushover_enabled

    def _should_send(self, level):
        if not self.enabled:
            return False

        configured_value = LEVEL_VALUES.get(
            self.minimum_level,
            10,
        )
        event_value = LEVEL_VALUES.get(level, 10)

        return event_value >= configured_value

    def _send_pushover(self, level, message):
        if not self.pushover_enabled:
            return

        try:
            user_key = get_secret(
                "guardian",
                "Guardian Pushover User Key",
            )

            api_token = get_secret(
                "guardian",
                "Guardian Pushover API Token",
            )

            payload = urllib.parse.urlencode(
                {
                    "token": api_token,
                    "user": user_key,
                    "title": f"Guardian {level}",
                    "message": message,
                    "priority": 0,
                }
            ).encode("utf-8")

            request = urllib.request.Request(
                self.PUSHOVER_URL,
                data=payload,
                method="POST",
            )

            with urllib.request.urlopen(
                request,
                timeout=10,
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            if result.get("status") != 1:
                print(
                    "NOTIFY ERROR [PUSHOVER] "
                    f"Unexpected response: {result}"
                )

        except (
            KeychainError,
            OSError,
            ValueError,
            urllib.error.URLError,
        ) as error:
            print(
                "NOTIFY ERROR [PUSHOVER] "
                f"{error}"
            )

        except Exception as error:
            print(
                "NOTIFY ERROR [PUSHOVER] "
                f"Unexpected failure: {error}"
            )

    def _send(self, level, message):
        if not self._should_send(level):
            return

        print(f"NOTIFY [{level}] {message}")

        self._send_pushover(
            level,
            message,
        )

    def mac_notification(self, title, message):
        """
        Show one native macOS Notification Center notification.
        """

        if not self.enabled:
            return False

        safe_title = (
            str(title)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )

        safe_message = (
            str(message)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )

        script = (
            f'display notification "{safe_message}" '
            f'with title "{safe_title}"'
        )

        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    script,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        except (
            subprocess.CalledProcessError,
            OSError,
        ) as error:
            print(
                "NOTIFY ERROR [MACOS] "
                f"{error}"
            )
            return False

        return True

    def info(self, message):
        self._send("INFO", message)

    def warning(self, message):
        self._send("WARNING", message)

    def error(self, message):
        self._send("ERROR", message)

    def critical(self, message):
        self._send("CRITICAL", message)