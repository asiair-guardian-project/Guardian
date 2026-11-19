from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    Capability,
    CapabilityStatus,
)
from modules.guardian_v1_application import GuardianV1Application
from modules.runtime_supervisor import RuntimeSupervisor


CONFIGURED_CAPABILITIES = {
    Capability.ASIAIR_MONITORING,
    Capability.OBSERVATORY_SAFETY_MONITORING,
    Capability.SAFETY_POWER_CONTROL,
    Capability.SAFETY_POWER_STATE_VERIFICATION,
    Capability.INDEPENDENT_MOUNT_MOTION,
    Capability.INDEPENDENT_MOUNT_STOP,
    Capability.MOUNT_STOP_VERIFICATION,
    Capability.MOUNT_CONNECTION_RECOVERY,
}


def test_application_starts_monitor_only():
    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_application_owns_capability_registry():
    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    assert isinstance(app.capabilities, CapabilityRegistry)
    assert (
        app.capabilities.configured_capabilities
        == frozenset(CONFIGURED_CAPABILITIES)
    )


def test_configured_capabilities_start_unknown():
    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    for capability in CONFIGURED_CAPABILITIES:
        assert (
            app.capabilities.status(capability)
            is CapabilityStatus.UNKNOWN
        )


def test_application_owns_runtime_supervisor():
    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    assert isinstance(app.supervisor, RuntimeSupervisor)


def test_application_applies_capability_probe_results():
    from modules.capability_probe import CapabilityProbeResult

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    app.apply_capability_probe_results(
        [
            CapabilityProbeResult(
                capability=Capability.ASIAIR_MONITORING,
                status=CapabilityStatus.AVAILABLE,
                observation=True,
                detail="ASIAIR reachable",
            ),
            CapabilityProbeResult(
                capability=Capability.INDEPENDENT_MOUNT_MOTION,
                status=CapabilityStatus.AVAILABLE,
                observation=None,
                detail="Wave independent motion path available",
            ),
        ]
    )

    assert (
        app.capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        app.capabilities.status(Capability.INDEPENDENT_MOUNT_MOTION)
        is CapabilityStatus.AVAILABLE
    )


def test_application_runs_single_result_probe():
    from modules.capability_probe import CapabilityProbeResult

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    calls = []

    def probe():
        calls.append("probe")
        return CapabilityProbeResult(
            capability=Capability.ASIAIR_MONITORING,
            status=CapabilityStatus.AVAILABLE,
            observation=True,
            detail="ASIAIR reachable",
        )

    results = app.run_capability_probe(probe)

    assert calls == ["probe"]
    assert len(results) == 1
    assert results[0].capability is Capability.ASIAIR_MONITORING
    assert (
        app.capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )


def test_application_runs_multi_result_probe():
    from modules.capability_probe import CapabilityProbeResult

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    def probe():
        return [
            CapabilityProbeResult(
                capability=Capability.INDEPENDENT_MOUNT_MOTION,
                status=CapabilityStatus.AVAILABLE,
                observation=None,
                detail="mount path available",
            ),
            CapabilityProbeResult(
                capability=Capability.INDEPENDENT_MOUNT_STOP,
                status=CapabilityStatus.AVAILABLE,
                observation=None,
                detail="mount path available",
            ),
        ]

    results = app.run_capability_probe(probe)

    assert len(results) == 2
    assert (
        app.capabilities.status(Capability.INDEPENDENT_MOUNT_MOTION)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        app.capabilities.status(Capability.INDEPENDENT_MOUNT_STOP)
        is CapabilityStatus.AVAILABLE
    )


def test_running_probe_does_not_enable_hardware_execution():
    from modules.capability_probe import CapabilityProbeResult

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    def probe():
        return CapabilityProbeResult(
            capability=Capability.ASIAIR_MONITORING,
            status=CapabilityStatus.AVAILABLE,
            observation=True,
            detail="ASIAIR reachable",
        )

    app.run_capability_probe(probe)

    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_application_runs_probe_cycle():
    from modules.capability_probe import CapabilityProbeResult

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    def asiair_probe():
        return CapabilityProbeResult(
            capability=Capability.ASIAIR_MONITORING,
            status=CapabilityStatus.AVAILABLE,
            observation=True,
            detail="ASIAIR reachable",
        )

    def mount_probe():
        return [
            CapabilityProbeResult(
                capability=Capability.INDEPENDENT_MOUNT_MOTION,
                status=CapabilityStatus.AVAILABLE,
                observation=None,
                detail="mount path available",
            ),
            CapabilityProbeResult(
                capability=Capability.INDEPENDENT_MOUNT_STOP,
                status=CapabilityStatus.AVAILABLE,
                observation=None,
                detail="mount path available",
            ),
        ]

    results = app.run_probe_cycle(
        [asiair_probe, mount_probe]
    )

    assert len(results) == 3
    assert (
        app.capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        app.capabilities.status(Capability.INDEPENDENT_MOUNT_MOTION)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        app.capabilities.status(Capability.INDEPENDENT_MOUNT_STOP)
        is CapabilityStatus.AVAILABLE
    )
    assert app.mode.monitor_only is True


def test_application_shadow_runtime_protection_never_reaches_hardware():
    from modules.commissioning import (
        CommissioningCheck,
        CommissioningResult,
        CommissioningStatus,
    )
    from modules.guardian_types import (
        AsiairState,
        MountMotionState,
        RoofState,
        SessionState,
    )

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
    )

    # Make the required runtime capabilities healthy.
    app.capabilities.update_many(
        {
            Capability.ASIAIR_MONITORING:
                CapabilityStatus.AVAILABLE,
            Capability.OBSERVATORY_SAFETY_MONITORING:
                CapabilityStatus.AVAILABLE,
            Capability.SAFETY_POWER_CONTROL:
                CapabilityStatus.AVAILABLE,
            Capability.INDEPENDENT_MOUNT_MOTION:
                CapabilityStatus.AVAILABLE,
            Capability.INDEPENDENT_MOUNT_STOP:
                CapabilityStatus.AVAILABLE,
            Capability.MOUNT_STOP_VERIFICATION:
                CapabilityStatus.AVAILABLE,
        }
    )

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint="config-a",
    )

    hardware_calls = []

    # First cycle establishes an imaging-permitted session.
    first = app.evaluate_runtime_cycle(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        commissioning=commissioning,
        configuration_fingerprint="config-a",
        execute_action=lambda action: hardware_calls.append(
            ("action", action)
        ),
        execute_safety_power=lambda roles: hardware_calls.append(
            ("power", roles)
        ),
    )

    assert first.session.state is SessionState.IMAGING_PERMITTED
    assert hardware_calls == []

    # Roof closure triggers protection.
    second = app.evaluate_runtime_cycle(
        armed=True,
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        commissioning=commissioning,
        configuration_fingerprint="config-a",
        execute_action=lambda action: hardware_calls.append(
            ("action", action)
        ),
        execute_safety_power=lambda roles: hardware_calls.append(
            ("power", roles)
        ),
    )

    assert second.session.state is SessionState.ABORTED
    assert second.incident is not None
    # Simulated power actions remain physically unresolved.
    from modules.guardian_types import ProtectionAction

    assert set(second.incident.unresolved_actions) == {
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    }
    assert hardware_calls == []

    # Runtime evaluation must not arm hardware execution.
    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_application_evaluates_normalized_observation():
    from modules.commissioning import (
        CommissioningCheck,
        CommissioningResult,
        CommissioningStatus,
    )
    from modules.guardian_types import (
        AsiairState,
        Capability,
        CapabilityStatus,
        MountMotionState,
        RoofState,
        SessionState,
    )
    from modules.guardian_v1_observation import GuardianV1Observation

    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
    }

    app = GuardianV1Application(
        configured_capabilities=configured,
    )

    app.capabilities.update_many(
        {
            Capability.ASIAIR_MONITORING: CapabilityStatus.AVAILABLE,
            Capability.OBSERVATORY_SAFETY_MONITORING:
                CapabilityStatus.AVAILABLE,
            Capability.SAFETY_POWER_CONTROL: CapabilityStatus.AVAILABLE,
        }
    )

    fingerprint = "test-configuration"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    observation = GuardianV1Observation(
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        mount_motion=MountMotionState.MOVING,
    )

    result = app.evaluate_observation(
        armed=True,
        observation=observation,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=lambda action: None,
    )

    assert result.session.state is SessionState.IMAGING_PERMITTED
    assert result.incident is None


def test_shadow_mode_roof_closure_reaches_protection_without_hardware():
    from modules.commissioning import (
        CommissioningCheck,
        CommissioningResult,
        CommissioningStatus,
    )
    from modules.guardian_types import (
        AsiairState,
        Capability,
        CapabilityStatus,
        MountMotionState,
        RoofState,
        SessionState,
    )
    from modules.guardian_v1_observation import GuardianV1Observation

    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
    }

    app = GuardianV1Application(
        configured_capabilities=configured,
    )

    app.capabilities.update_many(
        {
            capability: CapabilityStatus.AVAILABLE
            for capability in configured
        }
    )

    fingerprint = "shadow-roof-test"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    executed_actions = []

    safe_observation = GuardianV1Observation(
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        mount_motion=MountMotionState.MOVING,
    )

    initial = app.evaluate_observation(
        armed=True,
        observation=safe_observation,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    assert initial.session.state is SessionState.IMAGING_PERMITTED
    assert initial.incident is None

    closed_observation = GuardianV1Observation(
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        mount_motion=MountMotionState.MOVING,
    )

    protected = app.evaluate_observation(
        armed=True,
        observation=closed_observation,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    assert protected.session.state is SessionState.ABORTED
    assert protected.incident is not None

    # Guardian recognized the protection event, but shadow mode must
    # prevent every physical hardware action.
    assert executed_actions == []


def test_application_missing_recovery_file_blocks_arm(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=GuardianV1RecoveryStore(tmp_path / "missing.json"),
    )

    assert app.supervisor.recovery_blocked
    assert app.supervisor.incident is None
    assert app.mode.hardware_execution_enabled is False


def test_application_corrupt_recovery_file_blocks_arm(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    path = tmp_path / "recovery.json"
    path.write_text("{invalid", encoding="utf-8")

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=GuardianV1RecoveryStore(path),
    )

    assert app.supervisor.recovery_blocked
    assert app.supervisor.incident is None


def test_application_clean_recovery_state_loads(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = RuntimeSupervisor().export_recovery_state()
    state["shutdown_clean"] = True
    store.write(state)

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    )

    assert not app.supervisor.recovery_blocked
    assert app.supervisor.incident is None


def test_application_interrupted_imaging_blocks_arm(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = RuntimeSupervisor().export_recovery_state()
    state["session_state"] = "IMAGING_PERMITTED"
    store.write(state)

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    )

    assert app.supervisor.recovery_blocked
    assert app.supervisor.incident is None


def test_application_recovery_startup_never_calls_hardware(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = RuntimeSupervisor().export_recovery_state()
    state["shutdown_clean"] = True
    store.write(state)

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    )

    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_recovery_cannot_be_reloaded_after_startup(tmp_path):
    import pytest
    from modules.guardian_v1_recovery_store import (
        GuardianV1RecoveryStore,
        RecoveryStateError,
    )

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = RuntimeSupervisor().export_recovery_state()
    state["shutdown_clean"] = True
    store.write(state)

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    )

    app.supervisor.block_recovery("Newer in-memory safety state")

    with pytest.raises(RecoveryStateError):
        app.load_recovery_state()

    assert app.supervisor.recovery_blocked
    assert (
        app.supervisor.recovery_block_reason
        == "Newer in-memory safety state"
    )


def test_failed_startup_load_cannot_be_retried(tmp_path):
    import pytest
    from modules.guardian_v1_recovery_store import (
        GuardianV1RecoveryStore,
        RecoveryStateError,
    )

    store = GuardianV1RecoveryStore(tmp_path / "missing.json")

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    )

    assert app.supervisor.recovery_blocked

    state = RuntimeSupervisor().export_recovery_state()
    state["shutdown_clean"] = True
    store.write(state)

    with pytest.raises(RecoveryStateError):
        app.load_recovery_state()

    assert app.supervisor.recovery_blocked


def test_pre_arm_marker_is_persisted(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = RuntimeSupervisor().export_recovery_state()
    state["shutdown_clean"] = True
    store.write(state)

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    )

    # No hardware or observation evaluation is needed to verify
    # the pre-ARM marker's persistence.
    from modules.guardian_types import (
        AsiairState,
        RoofState,
    )
    from modules.commissioning import CommissioningStatus

    app.evaluate_runtime_cycle(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        commissioning=CommissioningStatus(
            results={},
            configuration_fingerprint="test",
        ),
        configuration_fingerprint="test",
        execute_action=lambda action: None,
    )

    saved = store.read()
    assert saved["session_state"] == "IMAGING_PERMITTED"
    assert saved["shutdown_clean"] is False
    assert app.mode.hardware_execution_enabled is False


def test_failed_pre_arm_write_blocks_arm(tmp_path):
    from modules.guardian_v1_recovery_store import (
        GuardianV1RecoveryStore,
        RecoveryStateError,
    )
    from modules.guardian_types import AsiairState, RoofState, SessionState
    from modules.commissioning import CommissioningStatus

    class FailingStore(GuardianV1RecoveryStore):
        def write(self, state):
            raise RecoveryStateError("Simulated disk failure")

    path = tmp_path / "recovery.json"
    initial = GuardianV1RecoveryStore(path)
    state = RuntimeSupervisor().export_recovery_state()
    state["shutdown_clean"] = True
    initial.write(state)

    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=FailingStore(path),
    )

    result = app.evaluate_runtime_cycle(
        armed=True,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        commissioning=CommissioningStatus(
            results={},
            configuration_fingerprint="test",
        ),
        configuration_fingerprint="test",
        execute_action=lambda action: None,
    )

    assert app.supervisor.recovery_blocked
    assert result.session.state is SessionState.DISARMED
    assert app.mode.hardware_execution_enabled is False

# Step 126B: durable runtime and operator transitions.
def _recovery_app(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    store.write(RuntimeSupervisor().export_recovery_state())
    return GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=store,
    ), store


def _seed_incident(app):
    from modules.guardian_types import ProtectionTrigger, SafetyPowerResult, SessionState
    from modules.protection_coordinator import initiate_protection

    app.supervisor._incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.FAILED,
    )
    app.supervisor._session_state = SessionState.ABORTED


def test_126b_incident_retry_results_are_persisted(tmp_path):
    from modules.guardian_types import AsiairState, RoofState, SafetyPowerResult
    from modules.commissioning import CommissioningStatus

    app, store = _recovery_app(tmp_path)
    _seed_incident(app)
    app.evaluate_runtime_cycle(
        armed=False,
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        commissioning=CommissioningStatus(results={}, configuration_fingerprint="test"),
        configuration_fingerprint="test",
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    assert store.read()["active_incident"]["records"]
    assert len(store.read()["active_incident"]["records"]) == 6
    restarted = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES, recovery_store=store
    )
    assert restarted.supervisor.incident is not None
    assert restarted.supervisor.recovery_blocked


def test_126b_acknowledgment_persists_but_incident_remains(tmp_path):
    app, store = _recovery_app(tmp_path)
    _seed_incident(app)
    assert app.acknowledge_abort()
    assert store.read()["abort_acknowledged"] is True
    assert store.read()["active_incident"] is not None
    assert app.supervisor.incident is not None


def test_126b_failed_acknowledgment_write_does_not_acknowledge(tmp_path):
    from modules.guardian_v1_recovery_store import RecoveryStateError

    app, store = _recovery_app(tmp_path)
    _seed_incident(app)
    def fail(state):
        raise RecoveryStateError("disk unavailable")
    store.write = fail
    assert not app.acknowledge_abort()
    assert not app.supervisor.abort_acknowledged
    assert app.supervisor.incident is not None
    assert app.supervisor.recovery_blocked


def test_126b_operator_clearance_persists(tmp_path):
    app, store = _recovery_app(tmp_path)
    app.supervisor.block_recovery("Interrupted session")
    assert not app.clear_recovery_block(operator_inspected=False)
    assert app.clear_recovery_block(operator_inspected=True)
    assert store.read()["recovery_required"] is False
    restarted = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES, recovery_store=store
    )
    assert not restarted.supervisor.recovery_blocked


def test_126b_corrupt_recovery_is_not_overwritten_by_observation(tmp_path):
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
    from modules.guardian_types import AsiairState, RoofState
    from modules.commissioning import CommissioningStatus

    path = tmp_path / "recovery.json"
    path.write_text("{corrupt", encoding="utf-8")
    app = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=GuardianV1RecoveryStore(path),
    )
    app.evaluate_runtime_cycle(
        armed=False,
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        commissioning=CommissioningStatus(results={}, configuration_fingerprint="test"),
        configuration_fingerprint="test",
        execute_action=lambda action: None,
    )
    assert path.read_text(encoding="utf-8") == "{corrupt"
    assert app.supervisor.recovery_blocked


def test_126b_recovered_incident_release_is_durable(tmp_path):
    from modules.guardian_types import SafetyPowerResult
    from modules.protection_planner import build_protection_plan

    app, store = _recovery_app(tmp_path)
    _seed_incident(app)
    # Model a completed shutdown before a Guardian restart.
    app.supervisor._incident.retry_unresolved(
        lambda action: SafetyPowerResult.VERIFIED_OFF
    )
    store.write(app.supervisor.export_recovery_state())
    restarted = GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES, recovery_store=store
    )
    assert restarted.supervisor.recovery_blocked
    assert restarted.acknowledge_abort()
    assert not restarted.authorize_new_session()
    for action in build_protection_plan():
        assert restarted.supervisor.record_fresh_power_verification(
            action, SafetyPowerResult.VERIFIED_OFF
        )
    assert restarted.authorize_new_session()
    assert not restarted.supervisor.recovery_blocked
    assert store.read()["active_incident"] is None
    assert len(store.read()["incident_history"]) == 1
