"""Durable storage for Guardian emergency-recovery state."""

import json
import os
import tempfile
from pathlib import Path


class EmergencyStateError(Exception):
    """Emergency state cannot be read, validated, or saved."""


REQUIRED_FIELDS = {
    "schema_version",
    "session_state",
    "abort_reason",
    "operator_acknowledged",
    "emergency_retry_active",
    "protection_results",
}


def validate_state(state):
    if not isinstance(state, dict):
        raise EmergencyStateError("Emergency state must be an object.")

    missing = REQUIRED_FIELDS - state.keys()
    if missing:
        raise EmergencyStateError(
            f"Missing emergency-state fields: {sorted(missing)}"
        )

    if state["schema_version"] != 1:
        raise EmergencyStateError("Unsupported emergency-state version.")

    if state["session_state"] not in (
        "DISARMED",
        "EMERGENCY_IN_PROGRESS",
        "ABORTED",
    ):
        raise EmergencyStateError("Invalid persisted session state.")

    if not isinstance(state["abort_reason"], (str, type(None))):
        raise EmergencyStateError("Invalid abort reason.")

    for field in ("operator_acknowledged", "emergency_retry_active"):
        if type(state[field]) is not bool:
            raise EmergencyStateError(f"Invalid boolean: {field}")

    if not isinstance(state["protection_results"], dict):
        raise EmergencyStateError("Invalid protection results.")

    session_state = state["session_state"]
    acknowledged = state["operator_acknowledged"]
    retry_active = state["emergency_retry_active"]
    reason = state["abort_reason"]

    if session_state == "DISARMED":
        if acknowledged or retry_active or reason is not None:
            raise EmergencyStateError(
                "DISARMED record contains emergency state."
            )

    else:
        if not reason:
            raise EmergencyStateError(
                "Emergency record requires an abort reason."
            )

        if session_state == "EMERGENCY_IN_PROGRESS" and acknowledged:
            raise EmergencyStateError(
                "An in-progress emergency cannot be acknowledged."
            )

        if acknowledged and retry_active:
            raise EmergencyStateError(
                "Acknowledged emergency cannot have active retries."
            )

    return state


class EmergencyStateStore:
    def __init__(self, file_path):
        self.path = Path(file_path)

    def read(self):
        if not self.path.is_file():
            raise EmergencyStateError(
                f"Emergency-state file missing: {self.path}"
            )

        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise EmergencyStateError(
                f"Unable to read emergency state: {error}"
            ) from error

        return validate_state(state)

    def write(self, state):
        validate_state(state)

        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(state, temporary, indent=2, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())

            os.replace(temporary_path, self.path)

            # Best-effort directory sync for crash durability.
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        except OSError as error:
            raise EmergencyStateError(
                f"Unable to save emergency state: {error}"
            ) from error

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
