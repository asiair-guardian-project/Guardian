"""Step 126B additional regression checks: isolated, no hardware access."""

from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore, RecoveryStateError
from modules.guardian_types import AsiairState, RoofState, ProtectionTrigger, SafetyPowerResult, SessionState
from modules.commissioning import CommissioningStatus
from modules.protection_coordinator import initiate_protection
from modules.protection_planner import build_protection_plan
from modules.runtime_supervisor import RuntimeSupervisor
from modules.safety_power_manager import SafetyPowerRoleRecord


def make_app(tmp_path):
    store = GuardianV1RecoveryStore(tmp_path / 'recovery.json')
    store.write(RuntimeSupervisor().export_recovery_state())
    return GuardianV1Application(configured_capabilities=set(), recovery_store=store), store


def seed_incident(app):
    app.supervisor._incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.FAILED,
    )
    app.supervisor._session_state = SessionState.ABORTED


def cycle(app, action):
    return app.evaluate_runtime_cycle(
        armed=False, roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        commissioning=CommissioningStatus(results={}, configuration_fingerprint='test'),
        configuration_fingerprint='test', execute_action=action,
        execute_safety_power=lambda roles: [
            SafetyPowerRoleRecord(role=role, endpoint=None, result=action(role))
            for role in roles
        ],
    )


def test_failed_runtime_write_keeps_incident_and_blocks_arm(tmp_path):
    app, store = make_app(tmp_path)
    seed_incident(app)
    # Enable only the injected in-memory fake executor; no device adapters exist.
    app.mode.enable_hardware_execution()
    calls = []
    def verify(action):
        calls.append(action)
        return SafetyPowerResult.FAILED
    def fail(_state):
        raise RecoveryStateError('disk failure')
    store.write = fail
    cycle(app, verify)
    assert calls
    assert app.supervisor.incident is not None
    assert app.supervisor.recovery_blocked
    # A subsequent cycle must continue emergency retries despite the block.
    cycle(app, verify)
    assert len(calls) >= 2 * len(build_protection_plan())


def test_failed_operator_release_is_not_effective(tmp_path):
    app, store = make_app(tmp_path)
    seed_incident(app)
    app.supervisor._incident.retry_unresolved(lambda action: SafetyPowerResult.VERIFIED_OFF)
    assert app.acknowledge_abort()
    def fail(_state):
        raise RecoveryStateError('disk failure')
    store.write = fail
    assert not app.authorize_new_session()
    assert app.supervisor.incident is not None
    assert app.supervisor.abort_acknowledged
    assert app.supervisor.recovery_blocked


def test_failed_recovery_clearance_remains_blocked(tmp_path):
    app, store = make_app(tmp_path)
    app.supervisor.block_recovery('inspection needed')
    def fail(_state):
        raise RecoveryStateError('disk failure')
    store.write = fail
    assert not app.clear_recovery_block(operator_inspected=True)
    assert app.supervisor.recovery_blocked


def test_restarted_incident_does_not_trust_old_verified_off(tmp_path):
    app, store = make_app(tmp_path)
    seed_incident(app)
    app.supervisor._incident.retry_unresolved(lambda action: SafetyPowerResult.VERIFIED_OFF)
    store.write(app.supervisor.export_recovery_state())
    restarted = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
    assert restarted.acknowledge_abort()
    assert not restarted.authorize_new_session()
    for action in build_protection_plan():
        assert restarted.supervisor.record_fresh_power_verification(action, SafetyPowerResult.VERIFIED_OFF)
    assert restarted.authorize_new_session()
    assert store.read()['active_incident'] is None


def test_disarmed_snapshot_restarts_without_false_incident(tmp_path):
    app, store = make_app(tmp_path)
    cycle(app, lambda action: (_ for _ in ()).throw(AssertionError('unexpected hardware call')))
    restarted = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
    assert restarted.supervisor.incident is None
    assert restarted.supervisor.session_state is SessionState.DISARMED
    assert not restarted.supervisor.recovery_blocked


def test_corrupt_state_survives_failed_load_and_observation(tmp_path):
    path = tmp_path / 'recovery.json'
    path.write_text('not-json', encoding='utf-8')
    app = GuardianV1Application(configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(path))
    cycle(app, lambda action: (_ for _ in ()).throw(AssertionError('unexpected hardware call')))
    assert path.read_text(encoding='utf-8') == 'not-json'
    assert app.supervisor.recovery_blocked
