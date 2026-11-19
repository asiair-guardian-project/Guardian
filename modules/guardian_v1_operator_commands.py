"""Guardian v1 operator-command boundary.

This handler is deliberately inert until the owning Guardian runtime invokes it.
It never reads/writes the recovery JSON itself and never controls hardware.
A future local IPC server must dispatch onto the supervisor's owning thread,
not call this concurrently with runtime evaluation.
"""

from dataclasses import dataclass
import secrets


@dataclass(frozen=True)
class OperatorResponse:
    ok: bool
    code: str
    message: str

    def as_dict(self):
        return {"ok": self.ok, "code": self.code, "message": self.message}


class OperatorCommandHandler:
    """Process-local command authority; tokens are not persisted or reusable.

    Construct only inside the active Guardian runtime. A restart invalidates
    old tokens, and a newly created incident receives a different token.
    """

    def __init__(self, app):
        self.app = app
        self._incident = None
        self._token = None

    def current_incident_token(self):
        incident = self.app.supervisor.incident
        if incident is None:
            self._incident = None
            self._token = None
            return None
        if incident is not self._incident:
            self._incident = incident
            self._token = secrets.token_hex(32)
        return self._token

    def handle(self, request):
        return handle_operator_command(self.app, request, expected_token=self.current_incident_token())


def handle_operator_command(app, request, *, expected_token=None):
    """Handle a single confirmed ACK or RELEASE; never ARM or touch hardware.

    Must be called on the same serialized execution context as Guardian's
    runtime supervisor. Does not start a server or listen on a network port.
    """
    if not isinstance(request, dict) or set(request) != {"command", "incident_id", "confirmed"}:
        return OperatorResponse(False, "INVALID_REQUEST", "Unexpected command fields")
    if request["command"] not in ("ACKNOWLEDGE_ABORT", "RELEASE_ABORT"):
        return OperatorResponse(False, "UNSUPPORTED", "Only acknowledging or releasing an abort is supported")
    if request["confirmed"] is not True:
        return OperatorResponse(False, "CONFIRMATION_REQUIRED", "Explicit confirmation required")
    if not isinstance(request["incident_id"], str) or len(request["incident_id"]) != 64:
        return OperatorResponse(False, "INVALID_REQUEST", "Invalid incident identifier")
    if app.recovery_store is None:
        return OperatorResponse(False, "NO_RECOVERY_STORE", "Durable recovery is required")
    incident = app.supervisor.incident
    if incident is None:
        return OperatorResponse(False, "NO_INCIDENT", "No active incident")
    if expected_token is None or expected_token != request["incident_id"]:
        return OperatorResponse(False, "STALE_INCIDENT", "Incident has changed; refresh the display")
    if request["command"] == "RELEASE_ABORT":
        if not app.supervisor.abort_acknowledged:
            return OperatorResponse(False, "NOT_ACKNOWLEDGED", "Acknowledge the abort first")
        blocker = app.release_blocker()
        if blocker is not None:
            return OperatorResponse(False, "RELEASE_REFUSED", blocker)
        if not app.authorize_new_session():
            return OperatorResponse(False, "PERSISTENCE_FAILED", "Release was not saved; the abort stays latched")
        return OperatorResponse(
            True, "RELEASED",
            "Abort released; session is DISARMED. Nothing was armed or powered on; ARM is a separate step")
    if app.supervisor.abort_acknowledged:
        return OperatorResponse(False, "ALREADY_ACKNOWLEDGED", "Already acknowledged")
    if not app.acknowledge_abort():
        return OperatorResponse(False, "PERSISTENCE_FAILED", "Acknowledgment was not saved")
    return OperatorResponse(
        True, "ACKNOWLEDGED",
        "Incident acknowledged; ARM stays blocked until you release the abort (ALLOW NEW SESSION)")
