"""Releasing an acknowledged, resolved abort: command, status, wording, and a full simulated night."""

import copy
from pathlib import Path
import socket as socket_module
import threading
from datetime import datetime, timedelta, timezone

import pytest

from modules.guardian_types import ProtectionTrigger, SafetyPowerResult, SessionState
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_commands import OperatorCommandHandler
from modules.guardian_v1_operator_socket import operator_status
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_sim_night import SimRig, build_sim_monitor, prepare_folder
from modules.protection_coordinator import initiate_protection
from modules.runtime_supervisor import RuntimeSupervisor


class MemoryStore:
    def __init__(self):
        self.saved = None
        self.fail = False
        self.path = Path("memory-store.json")

    def read(self):
        from modules.guardian_v1_recovery_store import RecoveryStateError
        if self.saved is None:
            raise RecoveryStateError("missing")
        return self.saved

    def write(self, state):
        from modules.guardian_v1_recovery_store import RecoveryStateError
        if self.fail:
            raise RecoveryStateError("simulated failure")
        self.saved = state


def make(result):
    """An application with an open incident whose power-off actions all returned `result`."""
    store = MemoryStore()
    store.write(RuntimeSupervisor().export_recovery_state())     # a normal, healthy recovery file
    app = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED}, execute_action=lambda action: result)
    app.supervisor._incident = incident
    app.supervisor._session_state = SessionState.ABORTED
    store.write(app.supervisor.export_recovery_state())
    handler = OperatorCommandHandler(app)
    return app, store, handler


def request(handler, command, confirmed=True, incident_id=None):
    return {"command": command, "confirmed": confirmed,
            "incident_id": incident_id or handler.current_incident_token()}


# ---- release_blocker never disagrees with authorize_new_session ------------------------

def scenarios():
    yield "no incident", lambda app: None
    yield "open, not acknowledged", lambda app: None
    yield "acknowledged", lambda app: app.acknowledge_abort()
    yield "acknowledged, recovery blocked", lambda app: (app.acknowledge_abort(), app.supervisor.block_recovery("test"))


@pytest.mark.parametrize("result", [SafetyPowerResult.VERIFIED_OFF, SafetyPowerResult.FAILED])
def test_release_blocker_matches_authorize_new_session(result):
    for name, prepare in scenarios():
        app, store, handler = make(result)
        if name == "no incident":
            app.supervisor._incident = None
        prepare(app)
        blocker = app.release_blocker()
        trial = copy.deepcopy(app.supervisor)
        assert (blocker is None) == bool(trial.authorize_new_session()), (name, result, blocker)


# ---- the command ---------------------------------------------------------------------

def test_release_before_acknowledging_is_refused():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    response = handler.handle(request(handler, "RELEASE_ABORT"))
    assert response.code == "NOT_ACKNOWLEDGED"
    assert app.supervisor.incident is not None


def test_release_with_unresolved_power_off_is_refused():
    app, store, handler = make(SafetyPowerResult.FAILED)
    assert handler.handle(request(handler, "ACKNOWLEDGE_ABORT")).ok
    response = handler.handle(request(handler, "RELEASE_ABORT"))
    assert response.code == "RELEASE_REFUSED" and "unresolved" in response.message.lower()
    assert app.supervisor.incident is not None


def test_release_after_acknowledging_a_resolved_abort_returns_to_disarmed_and_persists():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    assert handler.handle(request(handler, "ACKNOWLEDGE_ABORT")).ok
    response = handler.handle(request(handler, "RELEASE_ABORT"))
    assert response.ok and response.code == "RELEASED"
    assert app.supervisor.incident is None
    assert app.supervisor.session_state is SessionState.DISARMED
    assert store.saved["incident"] is None if "incident" in store.saved else True
    restarted = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
    assert restarted.supervisor.incident is None


def test_release_needs_confirmation_and_the_current_incident_token():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    assert handler.handle(request(handler, "ACKNOWLEDGE_ABORT")).ok
    assert handler.handle(request(handler, "RELEASE_ABORT", confirmed=False)).code == "CONFIRMATION_REQUIRED"
    assert handler.handle(request(handler, "RELEASE_ABORT", incident_id="0" * 64)).code == "STALE_INCIDENT"
    assert app.supervisor.incident is not None


def test_a_failed_save_keeps_the_abort_latched():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    assert handler.handle(request(handler, "ACKNOWLEDGE_ABORT")).ok
    store.fail = True
    response = handler.handle(request(handler, "RELEASE_ABORT"))
    assert response.code == "PERSISTENCE_FAILED"
    assert app.supervisor.incident is not None
    assert app.supervisor.session_state is SessionState.ABORTED


def test_release_with_no_incident_is_refused():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    app.supervisor._incident = None
    assert handler.handle({"command": "RELEASE_ABORT", "incident_id": "0" * 64, "confirmed": True}).code == "NO_INCIDENT"


def test_unrelated_commands_stay_unsupported():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    for command in ("AUTHORIZE_NEW_SESSION", "ARM", "POWER_ON"):
        assert handler.handle(request(handler, command)).code == "UNSUPPORTED"


def test_release_never_arms_and_never_calls_hardware():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    assert handler.handle(request(handler, "ACKNOWLEDGE_ABORT")).ok
    assert handler.handle(request(handler, "RELEASE_ABORT")).ok
    assert app.supervisor.session_state is SessionState.DISARMED     # not IMAGING_PERMITTED


# ---- status ----------------------------------------------------------------------------

def test_status_reports_when_release_is_available():
    app, store, handler = make(SafetyPowerResult.VERIFIED_OFF)
    status = operator_status(app, handler)
    assert status["release_available"] is False and "acknowledged" in status["release_unavailable_reason"]
    handler.handle(request(handler, "ACKNOWLEDGE_ABORT"))
    status = operator_status(app, handler)
    assert status["release_available"] is True and status["release_unavailable_reason"] is None
    assert status["acknowledged"] is True and status["incident_id"]
    handler.handle(request(handler, "RELEASE_ABORT"))
    status = operator_status(app, handler)
    assert status["release_available"] is False and status["incident_active"] is False


def test_status_with_unresolved_actions_says_why():
    app, store, handler = make(SafetyPowerResult.FAILED)
    handler.handle(request(handler, "ACKNOWLEDGE_ABORT"))
    status = operator_status(app, handler)
    assert status["release_available"] is False and "unresolved" in status["release_unavailable_reason"].lower()


# ---- a whole simulated night, with the real runtime ----------------------------------------

class Night:
    def __init__(self, tmp_path):
        # tmp_path is None -> short /tmp folder (macOS limits Unix socket paths to ~104 characters)
        self.folder = prepare_folder(None if tmp_path is None else tmp_path / "gr")
        self.now = datetime.now(timezone.utc)
        self.rig = SimRig(self.folder, say=lambda text: None, clock=lambda: self.now)
        self.runner = build_sim_monitor(self.folder, self.rig)
        self.app, self.gate = self.runner.application, self.runner.gate
        self.app.mode.enable_hardware_execution()

    def cycles(self, count, seconds=5):
        for _ in range(count):
            self.now += timedelta(seconds=seconds)
            self.gate.cycle(now=self.now)

    @property
    def handler(self):
        return self.runner.socket.handler


def test_full_night_abort_acknowledge_release_rearm(tmp_path):
    night = Night(tmp_path)
    night.cycles(3)
    assert night.gate.arm() is True
    night.cycles(4)
    assert night.app.supervisor.session_state is SessionState.IMAGING_PERMITTED

    night.rig.set_roof("CLOSED")
    night.cycles(16)
    assert night.rig.cuts == [2, 3, 4]                        # the real shutdown path cut all three
    assert night.app.supervisor.incident is not None
    assert night.gate.armed is False
    assert "must be acknowledged first" in night.gate.refusal_reason()

    assert night.handler.handle(request(night.handler, "ACKNOWLEDGE_ABORT")).ok
    assert "release it" in night.gate.refusal_reason()
    assert night.gate.arm() is False                           # acknowledging alone still does not allow ARM

    night.rig.set_roof("OPEN")
    night.cycles(4)
    assert night.gate.arm() is False                           # roof is open again, but the abort is still latched

    assert night.handler.handle(request(night.handler, "RELEASE_ABORT")).code == "RELEASED"
    assert night.app.supervisor.incident is None
    assert night.app.supervisor.session_state is SessionState.DISARMED
    assert night.rig.cuts == [2, 3, 4]                        # releasing switched nothing

    night.rig.power_everything_back_on()                      # the operator restores power by hand
    assert night.gate.arm() is True
    night.cycles(16)                                          # the roof must read OPEN for about a minute
    assert night.app.supervisor.session_state is SessionState.IMAGING_PERMITTED


def test_a_release_survives_a_restart_and_an_unreleased_abort_does_too(tmp_path):
    night = Night(tmp_path)
    night.cycles(3)
    assert night.gate.arm()
    night.cycles(4)
    night.rig.set_roof("CLOSED")
    night.cycles(16)
    night.handler.handle(request(night.handler, "ACKNOWLEDGE_ABORT"))

    recovery = night.folder / "recovery.json"
    app2 = GuardianV1Application(configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(recovery))
    assert app2.supervisor.incident is not None and app2.supervisor.abort_acknowledged   # still latched after restart

    night.handler.handle(request(night.handler, "RELEASE_ABORT"))
    app3 = GuardianV1Application(configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(recovery))
    assert app3.supervisor.incident is None                                              # release is durable


def test_the_simulated_night_never_uses_the_live_paths(tmp_path):
    night = Night(tmp_path)
    for path in (night.runner.socket.path, night.folder / "recovery.json"):
        assert str(night.folder) in str(path)
        assert "Application Support" not in str(path)


def test_the_rehearsal_folder_must_be_new_and_empty(tmp_path):
    folder = prepare_folder(tmp_path / "gr")
    with pytest.raises(FileExistsError):
        prepare_folder(folder)


def test_release_over_the_real_socket():
    night = Night(None)
    night.cycles(3)
    night.gate.arm()
    night.cycles(4)
    night.rig.set_roof("CLOSED")
    night.cycles(16)
    night.runner.socket.start()

    def ask(payload):
        import json
        box = {}

        def client():
            conn = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
            conn.settimeout(5)
            conn.connect(str(night.runner.socket.path))
            conn.sendall(json.dumps(payload).encode() + b"\n")
            data = b""
            while b"\n" not in data:
                data += conn.recv(4096)
            box["reply"] = json.loads(data)
            conn.close()

        thread = threading.Thread(target=client)
        thread.start()
        for _ in range(40):
            night.runner.socket.serve_once()
            if not thread.is_alive():
                break
        thread.join(5)
        return box["reply"]

    try:
        status = ask({"command": "STATUS"})
        assert status["incident_active"] and not status["release_available"]
        ack = ask({"command": "ACKNOWLEDGE_ABORT", "incident_id": status["incident_id"], "confirmed": True})
        assert ack["code"] == "ACKNOWLEDGED"
        status = ask({"command": "STATUS"})
        assert status["release_available"] is True
        released = ask({"command": "RELEASE_ABORT", "incident_id": status["incident_id"], "confirmed": True})
        assert released["code"] == "RELEASED"
        assert ask({"command": "STATUS"})["incident_active"] is False
    finally:
        night.runner.socket.close()
