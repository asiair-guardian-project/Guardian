from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import (
    CommissioningResult,
    CommissioningStatus,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    MountMotionState,
    MountStopResult,
    ProtectionAction,
    RoofState,
    SafetyPowerResult,
    SessionState,
)
from modules.runtime_supervisor import RuntimeSupervisor


def commissioned():
    return CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in REQUIRED_COMMISSIONING_CHECKS
        },
        configuration_fingerprint="config-a",
    )


def available_capabilities():
    return {
        capability: CapabilityStatus.AVAILABLE
        for capability in REQUIRED_CAPABILITIES
    }


def wave_protection_capabilities():
    capabilities = available_capabilities()
    capabilities[Capability.INDEPENDENT_MOUNT_STOP] = CapabilityStatus.AVAILABLE
    capabilities[Capability.MOUNT_STOP_VERIFICATION] = CapabilityStatus.AVAILABLE
    return capabilities


def recording_protection_executor(attempts):
    def execute_action(action):
        attempts.append(action)

        if action in (
            ProtectionAction.REQUEST_MOUNT_STOP,
            ProtectionAction.VERIFY_MOUNT_STOP,
        ):
            return MountStopResult.SUCCEEDED

        return SafetyPowerResult.FAILED

    return execute_action


def cycle(
    supervisor,
    *,
    roof_state=RoofState.OPEN,
    asiair_state=AsiairState.ONLINE,
    execute_action,
    capability_statuses=None,
):
    if capability_statuses is None:
        capability_statuses = available_capabilities()

    return supervisor.evaluate(
        armed=True,
        roof_state=roof_state,
        asiair_state=asiair_state,
        commissioning=commissioned(),
        configuration_fingerprint="config-a",
        capability_statuses=capability_statuses,
        execute_action=execute_action,
    )


def test_supervisor_persists_pre_imaging_state_between_cycles():
    supervisor = RuntimeSupervisor()

    result = cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert result.session.state is SessionState.WAITING_FOR_ROOF
    assert supervisor.session_state is SessionState.WAITING_FOR_ROOF
    assert supervisor.incident is None

    result = cycle(
        supervisor,
        roof_state=RoofState.OPEN,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert result.session.state is SessionState.IMAGING_PERMITTED
    assert supervisor.session_state is SessionState.IMAGING_PERMITTED


def test_supervisor_retains_incident_after_abort():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    result = cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert result.session.state is SessionState.ABORTED
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident is result.incident


def test_aborted_supervisor_retries_only_unresolved_power_action():
    supervisor = RuntimeSupervisor()
    attempts = []

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    def initial_execute(action):
        attempts.append(action)

        if action is ProtectionAction.SAFETY_POWER_OFF_MOUNT:
            return SafetyPowerResult.FAILED

        return SafetyPowerResult.VERIFIED_OFF

    first = cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=initial_execute,
    )

    assert first.session.state is SessionState.ABORTED
    assert first.incident is not None
    assert first.incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT
    ]

    attempts.clear()

    second = cycle(
        supervisor,
        roof_state=RoofState.OPEN,
        execute_action=lambda action: (
            attempts.append(action)
            or SafetyPowerResult.VERIFIED_OFF
        ),
    )

    assert second.session.state is SessionState.ABORTED
    assert attempts == [ProtectionAction.SAFETY_POWER_OFF_MOUNT]
    assert second.incident.unresolved_actions == []


def test_resolved_aborted_incident_executes_no_more_actions():
    supervisor = RuntimeSupervisor()
    attempted = []

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    result = cycle(
        supervisor,
        roof_state=RoofState.OPEN,
        execute_action=lambda action: (
            attempted.append(action)
            or SafetyPowerResult.VERIFIED_OFF
        ),
    )

    assert result.session.state is SessionState.ABORTED
    assert attempted == []
    assert supervisor.incident is result.incident


def test_disarm_does_not_clear_aborted_incident():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    result = supervisor.evaluate(
        armed=False,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        commissioning=commissioned(),
        configuration_fingerprint="config-a",
        capability_statuses=available_capabilities(),
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert result.session.state is SessionState.ABORTED
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident is not None


def test_resolved_aborted_incident_requires_explicit_new_session_authorization():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    incident = supervisor.incident

    assert supervisor.session_state is SessionState.ABORTED
    assert not supervisor.authorize_new_session()
    assert supervisor.session_state is SessionState.ABORTED

    assert supervisor.acknowledge_abort()
    assert supervisor.authorize_new_session()

    assert supervisor.session_state is SessionState.DISARMED
    assert supervisor.incident is None
    assert incident in supervisor.incident_history
    assert not supervisor.abort_acknowledged



def test_acknowledge_abort_preserves_incident():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    incident = supervisor.incident
    records = list(incident.records)

    assert supervisor.acknowledge_abort()
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident is incident
    assert supervisor.incident.records == records


def test_acknowledge_abort_does_not_authorize_new_session():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert supervisor.acknowledge_abort()
    assert supervisor.session_state is SessionState.ABORTED


def test_acknowledge_abort_does_not_bypass_unresolved_shutdown():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.FAILED,
    )

    assert supervisor.acknowledge_abort()
    assert supervisor.incident.unresolved_actions
    assert not supervisor.reset_aborted_session()
    assert supervisor.session_state is SessionState.ABORTED



def test_reset_requires_operator_acknowledgment():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert not supervisor.reset_aborted_session()
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident is not None


def test_acknowledgment_alone_does_not_release_abort():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert supervisor.acknowledge_abort()
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident is not None


def test_unresolved_incident_cannot_be_reset():
    supervisor = RuntimeSupervisor()

    cycle(
        supervisor,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    def execute_action(action):
        if action is ProtectionAction.SAFETY_POWER_OFF_MOUNT:
            return SafetyPowerResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=execute_action,
    )

    assert supervisor.incident is not None
    assert supervisor.incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT
    ]

    assert not supervisor.reset_aborted_session()
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident is not None


def test_reset_without_incident_does_nothing():
    supervisor = RuntimeSupervisor()

    assert not supervisor.reset_aborted_session()
    assert supervisor.session_state is SessionState.DISARMED



POWER_SHUTDOWN = [
    ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
    ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
]


def test_roof_closure_requests_all_three_shutdowns():
    supervisor = RuntimeSupervisor()
    attempts = []

    execute = recording_protection_executor(attempts)

    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=execute)

    result = cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=execute,
    )

    assert result.session.state is SessionState.ABORTED
    assert supervisor.incident is result.incident
    assert attempts == POWER_SHUTDOWN
    assert result.incident.unresolved_actions == POWER_SHUTDOWN


def test_unverified_shutdowns_are_retried_while_aborted():
    supervisor = RuntimeSupervisor()
    attempts = []
    execute = recording_protection_executor(attempts)

    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=execute)
    cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=execute)

    attempts.clear()

    result = cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=execute,
    )

    assert attempts == POWER_SHUTDOWN
    assert result.session.state is SessionState.ABORTED
    assert result.incident.unresolved_actions == POWER_SHUTDOWN


def test_roof_reopening_does_not_resume_aborted_session():
    supervisor = RuntimeSupervisor()
    attempts = []
    execute = recording_protection_executor(attempts)

    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=execute)
    cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=execute)

    incident = supervisor.incident
    attempts.clear()

    result = cycle(
        supervisor,
        roof_state=RoofState.OPEN,
        execute_action=execute,
    )

    assert result.session.state is SessionState.ABORTED
    assert supervisor.incident is incident
    assert attempts == POWER_SHUTDOWN


def test_verified_shutdowns_are_not_repeated():
    supervisor = RuntimeSupervisor()
    attempts = []

    def verified(action):
        attempts.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=verified)
    cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=verified)

    assert attempts == POWER_SHUTDOWN
    assert supervisor.incident.unresolved_actions == []

    attempts.clear()

    result = cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=verified,
    )

    assert attempts == []
    assert result.session.state is SessionState.ABORTED
    assert supervisor.incident is result.incident


def test_retry_only_unverified_power_roles():
    supervisor = RuntimeSupervisor()
    attempts = []

    def partial_shutdown(action):
        attempts.append(action)
        if action is ProtectionAction.SAFETY_POWER_OFF_MOUNT:
            return SafetyPowerResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=partial_shutdown)
    cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=partial_shutdown)

    assert supervisor.incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT
    ]

    attempts.clear()

    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=partial_shutdown,
    )

    assert attempts == [ProtectionAction.SAFETY_POWER_OFF_MOUNT]
    assert supervisor.session_state is SessionState.ABORTED


def make_resolved_abort():
    supervisor = RuntimeSupervisor()
    cycle(
        supervisor,
        roof_state=RoofState.OPEN,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    cycle(
        supervisor,
        roof_state=RoofState.CLOSED,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    assert supervisor.session_state is SessionState.ABORTED
    assert supervisor.incident.unresolved_actions == []
    return supervisor


def test_restored_abort_requires_fresh_verification():
    original = make_resolved_abort()
    assert original.acknowledge_abort()

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(original.export_recovery_state())

    assert restored.session_state is SessionState.ABORTED
    assert restored.abort_acknowledged
    assert restored.incident is not None
    assert restored.incident.unresolved_actions == []
    assert not restored.authorize_new_session()


def test_restoration_preserves_records_without_executing_hardware():
    original = make_resolved_abort()
    snapshot = original.export_recovery_state()

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(snapshot)

    assert restored.export_recovery_state() == snapshot
    assert restored.session_state is SessionState.ABORTED


def test_all_three_roles_require_fresh_verification():
    original = make_resolved_abort()
    original.acknowledge_abort()

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(original.export_recovery_state())

    for action in POWER_SHUTDOWN[:-1]:
        assert restored.record_fresh_power_verification(
            action, SafetyPowerResult.VERIFIED_OFF
        )

    assert not restored.authorize_new_session()

    assert restored.record_fresh_power_verification(
        POWER_SHUTDOWN[-1], SafetyPowerResult.VERIFIED_OFF
    )

    assert restored.authorize_new_session()
    assert restored.session_state is SessionState.DISARMED
    assert restored.incident is None
    assert len(restored.incident_history) == 1


def test_failed_fresh_verification_invalidates_previous_success():
    original = make_resolved_abort()
    original.acknowledge_abort()

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(original.export_recovery_state())

    for action in POWER_SHUTDOWN:
        restored.record_fresh_power_verification(
            action, SafetyPowerResult.VERIFIED_OFF
        )

    restored.record_fresh_power_verification(
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        SafetyPowerResult.FAILED,
    )

    assert not restored.authorize_new_session()


def test_completed_incident_history_survives_restart():
    supervisor = make_resolved_abort()
    assert supervisor.acknowledge_abort()
    assert supervisor.authorize_new_session()

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(supervisor.export_recovery_state())

    assert restored.session_state is SessionState.DISARMED
    assert restored.incident is None
    assert len(restored.incident_history) == 1
    assert restored.export_recovery_state() == supervisor.export_recovery_state()


def test_invalid_recovery_does_not_partially_replace_supervisor():
    from modules.guardian_v1_recovery_store import RecoveryStateError

    supervisor = make_resolved_abort()
    before = supervisor.export_recovery_state()

    invalid = dict(before)
    invalid["incident_history"] = [{"invalid": True}]

    import pytest

    with pytest.raises(RecoveryStateError):
        supervisor.restore_recovery_state(invalid)

    assert supervisor.export_recovery_state() == before
    assert supervisor.session_state is SessionState.ABORTED


def test_recovery_block_prevents_arm():
    supervisor = RuntimeSupervisor()
    supervisor.block_recovery("Previous imaging session interrupted")

    attempts = []
    result = cycle(
        supervisor,
        roof_state=RoofState.OPEN,
        execute_action=lambda action: attempts.append(action),
    )

    assert supervisor.recovery_blocked
    assert result.session.state is SessionState.DISARMED
    assert supervisor.session_state is SessionState.DISARMED
    assert supervisor.incident is None
    assert attempts == []


def test_recovery_block_survives_observation_cycles():
    supervisor = RuntimeSupervisor()
    supervisor.block_recovery("Unclean restart")

    for roof in (RoofState.CLOSED, RoofState.OPEN):
        cycle(
            supervisor,
            roof_state=roof,
            execute_action=lambda action: SafetyPowerResult.SIMULATED,
        )

    assert supervisor.recovery_blocked
    assert supervisor.recovery_block_reason == "Unclean restart"


def test_recovery_block_requires_operator_inspection():
    supervisor = RuntimeSupervisor()
    supervisor.block_recovery("Interrupted imaging")

    assert not supervisor.clear_recovery_block(operator_inspected=False)
    assert supervisor.recovery_blocked

    assert supervisor.clear_recovery_block(operator_inspected=True)
    assert not supervisor.recovery_blocked
    assert supervisor.session_state is SessionState.DISARMED


def test_recovery_clearance_does_not_clear_incident():
    supervisor = make_resolved_abort()
    supervisor.block_recovery("Restart recovery required")

    assert not supervisor.clear_recovery_block(operator_inspected=True)
    assert supervisor.recovery_blocked
    assert supervisor.incident is not None
    assert supervisor.session_state is SessionState.ABORTED


def test_invalid_recovery_block_reason_is_rejected():
    import pytest

    supervisor = RuntimeSupervisor()

    with pytest.raises(ValueError):
        supervisor.block_recovery("")

    assert not supervisor.recovery_blocked


def test_interrupted_imaging_restores_as_recovery_blocked():
    original = RuntimeSupervisor()
    state = original.export_recovery_state()
    state["session_state"] = "IMAGING_PERMITTED"
    state["shutdown_clean"] = False

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(state)

    assert restored.recovery_blocked
    assert restored.session_state is SessionState.DISARMED
    assert restored.incident is None


def test_recovery_block_survives_repeated_restoration():
    original = RuntimeSupervisor()
    original.block_recovery("Interrupted session")

    state = original.export_recovery_state()
    assert state["recovery_required"] is True

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(state)

    assert restored.recovery_blocked
    assert restored.export_recovery_state()["recovery_required"] is True


def test_clean_disarmed_state_restores_without_recovery_block():
    original = RuntimeSupervisor()
    state = original.export_recovery_state()
    state["shutdown_clean"] = True

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(state)

    assert not restored.recovery_blocked
    assert restored.session_state is SessionState.DISARMED


def test_unclean_disarmed_state_without_latch_does_not_fabricate_abort():
    original = RuntimeSupervisor()
    state = original.export_recovery_state()

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(state)

    assert not restored.recovery_blocked
    assert restored.incident is None
    assert restored.session_state is SessionState.DISARMED


def test_explicit_recovery_latch_restores_even_when_disarmed():
    original = RuntimeSupervisor()
    state = original.export_recovery_state()
    state["recovery_required"] = True

    restored = RuntimeSupervisor()
    restored.restore_recovery_state(state)

    assert restored.recovery_blocked
    assert restored.incident is None
