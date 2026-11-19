"""Independent durable recovery-state storage for Guardian 1.0."""

import json
import os
import tempfile
from pathlib import Path


class RecoveryStateError(Exception):
    """Recovery state cannot be read, validated, or saved."""


REQUIRED_FIELDS = {
    "schema_version",
    "active_incident",
    "abort_acknowledged",
    "incident_history",
    "session_state",
    "shutdown_clean",
    "recovery_required",
}


def validate_recovery_state(state):
    """Validate the outer recovery-state envelope."""
    if not isinstance(state, dict):
        raise RecoveryStateError("Recovery state must be an object.")

    if set(state) != REQUIRED_FIELDS:
        raise RecoveryStateError("Invalid recovery-state fields.")

    if type(state["schema_version"]) is not int or state["schema_version"] != 2:
        raise RecoveryStateError("Unsupported recovery-state version.")

    if type(state["abort_acknowledged"]) is not bool:
        raise RecoveryStateError("Invalid acknowledgment flag.")

    if not isinstance(state["incident_history"], list):
        raise RecoveryStateError("Incident history must be a list.")

    active = state["active_incident"]
    if active is not None and not isinstance(active, dict):
        raise RecoveryStateError("Active incident must be an object or null.")

    if active is None and state["abort_acknowledged"]:
        raise RecoveryStateError("Cannot acknowledge a nonexistent incident.")

    from modules.guardian_types import SessionState

    session_name = state["session_state"]
    if not isinstance(session_name, str) or session_name not in SessionState.__members__:
        raise RecoveryStateError("Invalid persisted session state.")

    for field in ("shutdown_clean", "recovery_required"):
        if type(state[field]) is not bool:
            raise RecoveryStateError(f"Invalid {field} flag.")

    if active is not None:
        if session_name != SessionState.ABORTED.name:
            raise RecoveryStateError("Active incident requires ABORTED state.")
        if not state["recovery_required"]:
            raise RecoveryStateError("Active incident requires recovery latch.")

    if session_name == SessionState.ABORTED.name and not state["recovery_required"]:
        raise RecoveryStateError("ABORTED requires recovery.")

    if session_name == SessionState.IMAGING_PERMITTED.name:
        if state["shutdown_clean"]:
            raise RecoveryStateError("Imaging cannot be marked cleanly shut down.")

    if state["shutdown_clean"] and state["recovery_required"]:
        raise RecoveryStateError("Recovery-required state cannot be clean.")

    # Local import avoids a cycle with the incident codec's error type.
    from modules.guardian_v1_incident_codec import decode_incident

    if active is not None:
        decode_incident(active)

    for incident in state["incident_history"]:
        decode_incident(incident)

    return state


class GuardianV1RecoveryStore:
    """Atomic JSON storage isolated from legacy Guardian state."""

    def __init__(self, file_path):
        self.path = Path(file_path)

    def read(self):
        if not self.path.is_file():
            raise RecoveryStateError(
                f"Guardian 1.0 recovery state missing: {self.path}"
            )

        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RecoveryStateError(
                f"Unable to read recovery state: {error}"
            ) from error

        return validate_recovery_state(state)

    def write(self, state):
        validate_recovery_state(state)

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

            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        except (OSError, TypeError, ValueError) as error:
            raise RecoveryStateError(
                f"Unable to save recovery state: {error}"
            ) from error

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
