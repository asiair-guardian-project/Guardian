import json
from pathlib import Path


class StatusWriteError(Exception):
    """Raised when Guardian status cannot be written safely."""


def write_status(file_path, status_data):
    """Write Guardian status as JSON."""

    path = Path(file_path)

    try:
        path.write_text(
            json.dumps(
                status_data,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise StatusWriteError(
            f"Unable to write Guardian status: {error}"
        ) from error