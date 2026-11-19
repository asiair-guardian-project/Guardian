import json
from datetime import datetime
from pathlib import Path


class AlertManagerError(Exception):
    """Raised when persistent Guardian alert state cannot be managed."""


class AlertManager:
    """Maintains one persistent operator-action-required alert."""

    def __init__(self, file_path):
        self.file_path = Path(file_path)

    def set_alert(
        self,
        severity,
        source,
        event_type,
        message,
        protection_results=None,
    ):
        """
        Create or replace the current unresolved Guardian alert.
        """

        alert_data = {
            "active": True,
            "acknowledged": False,
            "timestamp": datetime.now().astimezone().isoformat(),
            "severity": severity,
            "source": source,
            "event_type": event_type,
            "message": message,
            "protection_results": protection_results or {},
        }

        try:
            self.file_path.write_text(
                json.dumps(
                    alert_data,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

        except OSError as error:
            raise AlertManagerError(
                f"Unable to write Guardian alert: {error}"
            ) from error

        return alert_data

    def read_alert(self):
        """
        Return the current alert, or None if no active alert exists.
        """

        if not self.file_path.exists():
            return None

        try:
            text = self.file_path.read_text(
                encoding="utf-8"
            ).strip()

        except OSError as error:
            raise AlertManagerError(
                f"Unable to read Guardian alert: {error}"
            ) from error

        if not text:
            return None

        try:
            alert_data = json.loads(text)

        except json.JSONDecodeError as error:
            raise AlertManagerError(
                f"Guardian alert file is invalid JSON: {error}"
            ) from error

        if not alert_data.get("active"):
            return None

        return alert_data

    def acknowledge(self):
        """
        Mark the current Guardian alert acknowledged and inactive.
        """

        alert_data = self.read_alert()

        if alert_data is None:
            return False

        alert_data["active"] = False
        alert_data["acknowledged"] = True
        alert_data["acknowledged_at"] = (
            datetime.now().astimezone().isoformat()
        )

        try:
            self.file_path.write_text(
                json.dumps(
                    alert_data,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

        except OSError as error:
            raise AlertManagerError(
                f"Unable to acknowledge Guardian alert: {error}"
            ) from error

        return True