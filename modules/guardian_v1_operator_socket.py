"""Local operator IPC, owned by the Guardian application process.

No background worker: call serve_once on the SAME thread as runtime evaluation.
This module does not create or load Guardian state and does not control hardware.
"""
import json
import os
from pathlib import Path
import socket
import stat

from modules.guardian_v1_operator_commands import OperatorCommandHandler

MAX_REQUEST = 4096


def _arm_available(app, sup, incident, gate):
    reason_of = getattr(gate, "refusal_reason", None)
    if reason_of is not None:
        return reason_of() is None
    return bool(gate is not None and not sup.recovery_blocked and incident is None and not app.mode.monitor_only)


def _arm_reason(gate):
    reason_of = getattr(gate, "refusal_reason", None)
    if reason_of is None or getattr(gate, "armed", False):
        return None
    return reason_of()


def operator_status(app, handler, gate=None, observation_provider=None, setup_provider=None):
    sup = app.supervisor
    incident = sup.incident
    result = {
        "ok": True,
        "code": "STATUS",
        "arm_blocked": bool(sup.recovery_blocked or incident is not None),
        "session": sup.session_state.name,
        "armed": bool(gate.armed) if gate is not None else False,
        "arm_available": _arm_available(app, sup, incident, gate),
        "arm_unavailable_reason": _arm_reason(gate),
        "hardware_execution_enabled": bool(app.mode.hardware_execution_enabled),
        "recovery_reason": sup.recovery_block_reason,
        "incident_active": incident is not None,
        "recovery_file": str(app.recovery_store.path.resolve()) if app.recovery_store else None,
        "acknowledged": sup.abort_acknowledged,
        "incident_id": handler.current_incident_token(),
        "unresolved_actions": [a.name for a in incident.unresolved_actions] if incident else [],
    }
    result["release_available"] = False
    result["release_unavailable_reason"] = None
    if incident is not None:
        try:
            blocker = app.release_blocker()
            result["release_available"] = blocker is None
            result["release_unavailable_reason"] = blocker
        except Exception:
            result["release_unavailable_reason"] = "Release status could not be determined"
    if observation_provider is not None:
        snapshot = observation_provider()
        if snapshot is not None:
            result["equipment"] = snapshot
    if setup_provider is not None:
        result["setup"] = setup_provider()
    return result


class GuardianOperatorSocket:
    """Non-threaded local socket. Owner must poll serve_once from Guardian loop."""
    def __init__(self, app, path, *, gate=None, observation_provider=None, setup_provider=None):
        if gate is not None and gate.application is not app:
            raise ValueError("ARM gate must belong to socket application")
        self.gate = gate
        self.observation_provider = observation_provider
        self.setup_provider = setup_provider
        self.app = app
        self.handler = OperatorCommandHandler(app)
        self.path = Path(path)
        self.server = None

    def _clear_stale_socket(self):
        """Remove the leftover socket of a Guardian that died without cleanup.

        A hard kill, crash or power loss leaves the socket file behind, and
        refusing to start because of it would keep a relaunched monitor down
        for good. This removes the file only when it is a socket owned by the
        current user that nobody is listening on. A symlink, a regular file,
        someone else's file, or a live listener (another Guardian running) is
        refused, exactly as before.
        """
        path = self.path
        if path.is_symlink():
            raise FileExistsError("Socket path is a symlink; refusing to touch it")
        info = os.lstat(path)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise FileExistsError(
                "Socket path already exists and is not a Guardian socket; refusing to unlink it"
            )
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(1)
            probe.connect(str(path))
        except (ConnectionRefusedError, FileNotFoundError):
            pass  # nobody is listening: the file is a leftover
        except OSError as error:
            raise FileExistsError(
                f"Socket path already exists and could not be confirmed stale: {error}"
            ) from error
        else:
            raise FileExistsError("Another Guardian is already listening on this socket")
        finally:
            probe.close()
        path.unlink()

    def start(self):
        directory = self.path.parent
        if not directory.is_dir():
            raise ValueError("Socket parent directory must already exist")
        st = directory.stat()
        if st.st_uid != os.getuid() or (stat.S_IMODE(st.st_mode) & 0o077):
            raise PermissionError("Socket directory must be owned by current user and mode 0700")
        if self.path.exists() or self.path.is_symlink():
            self._clear_stale_socket()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.server.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self.server.listen(4)
            self.server.settimeout(0.25)
        except BaseException:
            self.server.close()
            self.server = None
            raise

    def serve_once(self):
        if self.server is None:
            raise RuntimeError("Socket not started")
        try:
            connection, _ = self.server.accept()
        except socket.timeout:
            return False
        with connection:
            connection.settimeout(1)
            payload = bytearray()
            try:
                while len(payload) <= MAX_REQUEST:
                    part = connection.recv(min(1024, MAX_REQUEST + 1 - len(payload)))
                    if not part:
                        break
                    payload.extend(part)
                    if b"\n" in part:
                        break
                if len(payload) > MAX_REQUEST or b"\n" not in payload:
                    response = {"ok": False, "code": "INVALID_REQUEST", "message": "Request too large or unterminated"}
                else:
                    request = json.loads(payload.split(b"\n", 1)[0].decode("utf-8"))
                    if request == {"command": "STATUS"}:
                        response = operator_status(self.app, self.handler, self.gate, self.observation_provider, self.setup_provider)
                    elif isinstance(request, dict) and request.get("command") == "PREVIEW_SETUP":
                        if (self.setup_provider is None or
                                not callable(getattr(self.setup_provider, "preview", None))):
                            response = {"ok": False, "code": "UNAVAILABLE", "message": "Setup preview unavailable"}
                        elif set(request) != {"command", "changes"} or not isinstance(request["changes"], dict):
                            response = {"ok": False, "code": "INVALID_REQUEST", "message": "Expected changes mapping"}
                        else:
                            response = self.setup_provider.preview(request["changes"])
                    elif isinstance(request, dict) and request.get("command") == "STAGE_SETUP":
                        if (self.setup_provider is None or
                                not callable(getattr(self.setup_provider, "stage", None))):
                            response = {"ok": False, "code": "UNAVAILABLE", "message": "Setup staging unavailable"}
                        elif (set(request) != {"command", "changes", "expected_sha256"} or
                              not isinstance(request["changes"], dict) or
                              not isinstance(request["expected_sha256"], str)):
                            response = {"ok": False, "code": "INVALID_REQUEST", "message": "Invalid staging request"}
                        else:
                            response = self.setup_provider.stage(request["changes"], request["expected_sha256"])
                    elif isinstance(request, dict) and request.get("command") in ("ARM", "DISARM"):
                        response = self._handle_arm_command(request)
                    else:
                        response = self.handler.handle(request).as_dict()
            except (ValueError, UnicodeError, socket.timeout, OSError):
                response = {"ok": False, "code": "INVALID_REQUEST", "message": "Malformed request"}
            try:
                connection.sendall((json.dumps(response) + "\n").encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError):
                # A disconnected operator client must not stop monitoring.
                pass
        return True

    def _handle_arm_command(self, request):
        if self.gate is None:
            return {"ok": False, "code": "UNSUPPORTED", "message": "ARM controls unavailable"}
        if request == {"command": "DISARM", "confirmed": True}:
            ended = self.gate.disarm() is True
            return {"ok": True, "code": "DISARMED",
                    "message": ("ARM authorization revoked; session ended (DISARMED)" if ended
                                else "ARM authorization revoked")}
        if request == {"command": "ARM", "confirmed": True}:
            if self.gate.arm():
                return {"ok": True, "code": "ARMED", "message": "ARM authorized"}
            reason = getattr(self.gate, "last_refusal", None)
            return {"ok": False, "code": "ARM_BLOCKED",
                    "message": ("ARM refused: " + reason) if reason else
                    "Commissioning, recovery, session, or hardware gate prevents ARM"}
        return {"ok": False, "code": "INVALID_REQUEST", "message": "Explicit confirmation and exact command fields required"}

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server = None
            if self.path.is_socket():
                self.path.unlink()
