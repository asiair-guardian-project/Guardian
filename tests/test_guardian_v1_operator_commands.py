"""No-network, no-hardware operator command tests."""

from modules.guardian_types import Capability, ProtectionTrigger, SafetyPowerResult, SessionState
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_commands import OperatorCommandHandler
from modules.protection_coordinator import initiate_protection


class MemoryStore:
    def __init__(self):
        self.saved = None
        self.fail = False

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


def setup():
    store = MemoryStore()
    app = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.FAILED,
    )
    app.supervisor._incident = incident
    app.supervisor._session_state = SessionState.ABORTED
    store.write(app.supervisor.export_recovery_state())
    handler = OperatorCommandHandler(app)
    request = {"command": "ACKNOWLEDGE_ABORT", "incident_id": handler.current_incident_token(), "confirmed": True}
    return app, store, handler, request


def test_ack_is_durable_and_does_not_clear_abort():
    app, store, handler, req = setup()
    result = handler.handle(req)
    assert result.ok
    assert app.supervisor.abort_acknowledged
    assert app.supervisor.incident is not None
    assert app.supervisor.session_state is SessionState.ABORTED
    assert store.saved["abort_acknowledged"] is True
    assert len(app.supervisor.incident.unresolved_actions) == 3


def test_no_confirmation_is_rejected():
    app, store, handler, req = setup()
    req["confirmed"] = False
    assert not handler.handle(req).ok
    assert not app.supervisor.abort_acknowledged


def test_stale_incident_rejected():
    app, store, handler, req = setup()
    req["incident_id"] = "0" * 64
    assert handler.handle(req).code == "STALE_INCIDENT"


def test_storage_failure_fails_closed():
    app, store, handler, req = setup()
    store.fail = True
    assert handler.handle(req).code == "PERSISTENCE_FAILED"
    assert not app.supervisor.abort_acknowledged
    assert app.supervisor.incident is not None
    assert app.supervisor.recovery_blocked


def test_no_recovery_store_rejected():
    app, store, handler, req = setup()
    app.recovery_store = None
    assert handler.handle(req).code == "NO_RECOVERY_STORE"


def test_unsupported_commands_rejected():
    app, store, handler, req = setup()
    req["command"] = "AUTHORIZE_NEW_SESSION"
    assert handler.handle(req).code == "UNSUPPORTED"


def test_bad_request_rejected():
    app, store, handler, req = setup()
    req["power_on"] = True
    assert handler.handle(req).code == "INVALID_REQUEST"


def test_repeated_ack_rejected_without_mutation():
    app, store, handler, req = setup()
    assert handler.handle(req).ok
    assert handler.handle(req).code == "STALE_INCIDENT"


def test_restart_invalidates_token():
    app, store, handler, req = setup()
    new_handler = OperatorCommandHandler(app)
    assert new_handler.handle(req).code == "STALE_INCIDENT"


def test_new_incident_invalidates_token():
    app, store, handler, req = setup()
    app.supervisor._incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.FAILED,
    )
    assert handler.handle(req).code == "STALE_INCIDENT"
