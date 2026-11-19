from pathlib import Path


VALID_COMMANDS = {
    "ARM",
    "DISARM",
    "STATUS",
    "ACK",
    "ACK_ABORT",
}


class ControlCommandError(Exception):
    """Raised when a Guardian control command is invalid."""


def read_control_command(file_path):
    """
    Read one Guardian control command from a text file.

    Valid commands:
    - ARM
    - DISARM
    - STATUS
    - ACK
    - ACK_ABORT
    """

    path = Path(file_path)

    if not path.exists():
        return None

    if not path.is_file():
        raise ControlCommandError(
            f"Control path is not a file: {file_path}"
        )

    try:
        command = path.read_text(
            encoding="utf-8"
        ).strip().upper()
    except OSError as error:
        raise ControlCommandError(
            f"Unable to read control file: {error}"
        ) from error

    if not command:
        return None

    if command not in VALID_COMMANDS:
        raise ControlCommandError(
            f"Invalid Guardian control command: {command}"
        )

    return command


def clear_control_command(file_path):
    """Clear the control file after a command has been processed."""

    path = Path(file_path)

    try:
        path.write_text("", encoding="utf-8")
    except OSError as error:
        raise ControlCommandError(
            f"Unable to clear control file: {error}"
        ) from error