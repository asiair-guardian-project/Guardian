import json
import urllib.error
import urllib.request


class AlpacaSafetyMonitorError(Exception):
    """Raised when the Starfront Alpaca SafetyMonitor cannot be read."""

def read_alpaca_safety_status(
    host,
    port,
    device_number,
    timeout_seconds=5,
):
    """
    Read Starfront's Alpaca SafetyMonitor.
    """
    if not host:
        raise AlpacaSafetyMonitorError(
            "Alpaca SafetyMonitor host is not configured."
        )
    url = (
            f"https://{host}:{port}"
            f"/api/v1/safetymonitor/{device_number}/issafe"
        )
    try:
        with urllib.request.urlopen(
            url,
            timeout=timeout_seconds,
        ) as response:
            raw = response.read().decode("utf-8")

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as error:
        raise AlpacaSafetyMonitorError(
            f"Unable to read Alpaca SafetyMonitor: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AlpacaSafetyMonitorError(
            "Alpaca SafetyMonitor returned invalid JSON."
        ) from error

    error_number = payload.get("ErrorNumber", 0)

    if error_number != 0:
        error_message = payload.get(
            "ErrorMessage",
            "Unknown Alpaca error.",
        )
        raise AlpacaSafetyMonitorError(
            f"Alpaca error {error_number}: {error_message}"
        )

    if "Value" not in payload:
        raise AlpacaSafetyMonitorError(
            "Alpaca SafetyMonitor response is missing Value."
        )

    is_safe = payload["Value"]

    if not isinstance(is_safe, bool):
        raise AlpacaSafetyMonitorError(
            "Alpaca SafetyMonitor Value is not a boolean."
        )

    return {
        "is_safe": is_safe,
        "status": "OPEN" if is_safe else "CLOSED",
    }
