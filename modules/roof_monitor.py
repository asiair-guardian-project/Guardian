from datetime import datetime
from pathlib import Path


class RoofStatusError(Exception):
    """Raised when the Starfront roof status file cannot be interpreted."""


def read_roof_status(file_path):
    """
    Read a Starfront roof status file.

    Expected format example:
    2026-08-07 07:06:59AM CST Roof Status: CLOSED

    Returns a dictionary containing:
    - timestamp_text
    - timestamp
    - status
    - raw_line
    """

    if not file_path:
        raise RoofStatusError("Roof status file path is not configured.")

    path = Path(file_path)

    if not path.exists():
        raise RoofStatusError(
            f"Roof status file does not exist: {file_path}"
        )

    if not path.is_file():
        raise RoofStatusError(
            f"Roof status path is not a file: {file_path}"
        )

    try:
        raw_line = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RoofStatusError(
            f"Unable to read roof status file: {error}"
        ) from error

    if not raw_line:
        raise RoofStatusError("Roof status file is empty.")

    marker = "Roof Status:"

    if marker not in raw_line:
        raise RoofStatusError(
            "Roof status file does not contain 'Roof Status:'."
        )

    timestamp_text, status_text = raw_line.split(marker, 1)

    timestamp_text = timestamp_text.strip()
    status = status_text.strip().upper()

    if not timestamp_text:
        raise RoofStatusError(
            "Roof status file does not contain a timestamp."
        )

    if not status:
        raise RoofStatusError(
            "Roof status file does not contain a roof status."
        )

    try:
        timestamp = datetime.strptime(
            timestamp_text,
            "%Y-%m-%d %I:%M:%S%p %Z",
        )
    except ValueError as error:
        raise RoofStatusError(
            f"Invalid roof status timestamp: {timestamp_text}"
        ) from error

    return {
        "timestamp_text": timestamp_text,
        "timestamp": timestamp,
        "status": status,
        "raw_line": raw_line,
    }