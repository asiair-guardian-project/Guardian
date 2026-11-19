import pytest

from modules.guardian_types import (
    Capability,
    MountMotionState,
    MountStopResult,
    ProtectionAction,
    ProtectionTrigger,
    SafetyPowerResult,
    SessionState,
)
from modules.protection_coordinator import initiate_protection


def test_incident_requires_a_trigger():
    with pytest.raises(ValueError):
        initiate_protection(
            triggers=set(),
                execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
        )


def test_level_zero_incident_powers_off_all_three_devices():
    attempted = []

    def fake_execute(action):
        attempted.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=fake_execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
    assert incident.session_state is SessionState.ABORTED
    assert incident.unresolved_actions == []


def test_moving_mount_uses_three_device_shutdown_without_stop():
    attempted = []

    def fake_execute(action):
        attempted.append(action)

        if action is ProtectionAction.REQUEST_MOUNT_STOP:
            return MountStopResult.SUCCEEDED

        if action is ProtectionAction.VERIFY_MOUNT_STOP:
            return MountStopResult.SUCCEEDED

        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.ASIAIR_LOST},
        execute_action=fake_execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
    assert incident.session_state is SessionState.ABORTED


def test_roof_closure_with_moving_mount_uses_three_device_shutdown():
    attempted = []

    def fake_execute(action):
        attempted.append(action)

        if action is ProtectionAction.REQUEST_MOUNT_STOP:
            return MountStopResult.FAILED

        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=fake_execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
    assert incident.session_state is SessionState.ABORTED
    assert incident.unresolved_actions == []


def test_failed_power_action_is_recorded_unresolved_but_incident_is_aborted():
    def fake_execute(action):
        if action is ProtectionAction.SAFETY_POWER_OFF_ASIAIR:
            return SafetyPowerResult.FAILED

        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.PROTECTION_CAPABILITY_LOST},
        execute_action=fake_execute,
    )

    assert incident.session_state is SessionState.ABORTED
    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    ]


def test_multiple_triggers_are_preserved_in_incident():
    triggers = {
        ProtectionTrigger.ROOF_CLOSED,
        ProtectionTrigger.PROTECTION_CAPABILITY_LOST,
    }

    incident = initiate_protection(
        triggers=triggers,
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert incident.triggers == triggers


def test_incident_retry_resolves_failed_power_action_and_keeps_history():
    attempts = {ProtectionAction.SAFETY_POWER_OFF_ASIAIR: 0}

    def initial_execute(action):
        if action is ProtectionAction.SAFETY_POWER_OFF_ASIAIR:
            attempts[action] += 1
            return SafetyPowerResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=initial_execute,
    )

    assert incident.session_state is SessionState.ABORTED
    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    ]
    assert len(incident.records) == 3

    def retry_execute(action):
        assert action is ProtectionAction.SAFETY_POWER_OFF_ASIAIR
        return SafetyPowerResult.VERIFIED_OFF

    retry_records = incident.retry_unresolved(retry_execute)

    assert len(retry_records) == 1
    assert retry_records[0].result is SafetyPowerResult.VERIFIED_OFF
    assert incident.unresolved_actions == []
    assert incident.session_state is SessionState.ABORTED

    # Initial three attempts plus the successful retry remain in audit history.
    assert len(incident.records) == 4
    assert incident.records[0].result is SafetyPowerResult.FAILED
    assert incident.records[3].result is SafetyPowerResult.VERIFIED_OFF


def test_resolved_incident_does_not_repeat_power_actions():
    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    attempted = []

    def retry_execute(action):
        attempted.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    assert incident.retry_unresolved(retry_execute) == []
    assert attempted == []
    assert incident.session_state is SessionState.ABORTED


def test_incident_batches_required_safety_power_roles():
    from modules.guardian_types import SafetyPowerRole
    from modules.safety_power_manager import SafetyPowerRoleRecord

    batches = []

    def execute_action(action):
        raise AssertionError(
            f"unexpected per-action execution: {action}"
        )

    def execute_safety_power(roles):
        batches.append(set(roles))
        return [
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.ASIAIR,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.MOUNT,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.ACCESSORIES,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
        ]

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=execute_action,
        execute_safety_power=execute_safety_power,
    )

    assert batches == [{
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
        SafetyPowerRole.ACCESSORIES,
    }]
    assert incident.unresolved_actions == []
    assert len(incident.records) == 3


def test_incident_retry_batches_only_unresolved_safety_power_role():
    from modules.guardian_types import SafetyPowerRole
    from modules.safety_power_manager import SafetyPowerRoleRecord

    batches = []

    def execute_action(action):
        raise AssertionError(
            f"unexpected per-action execution: {action}"
        )

    def execute_safety_power(roles):
        batches.append(set(roles))

        if len(batches) == 1:
            return [
                SafetyPowerRoleRecord(
                    role=SafetyPowerRole.ASIAIR,
                    endpoint=None,
                    result=SafetyPowerResult.FAILED,
                ),
                SafetyPowerRoleRecord(
                    role=SafetyPowerRole.MOUNT,
                    endpoint=None,
                    result=SafetyPowerResult.VERIFIED_OFF,
                ),
                SafetyPowerRoleRecord(
                    role=SafetyPowerRole.ACCESSORIES,
                    endpoint=None,
                    result=SafetyPowerResult.VERIFIED_OFF,
                ),
            ]

        return [
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.ASIAIR,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
        ]

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=execute_action,
        execute_safety_power=execute_safety_power,
    )

    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    ]

    retry_records = incident.retry_unresolved(
        execute_action,
        execute_safety_power=execute_safety_power,
    )

    assert batches == [
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
            SafetyPowerRole.ACCESSORIES,
        },
        {
            SafetyPowerRole.ASIAIR,
        },
    ]

    assert len(retry_records) == 1
    assert incident.unresolved_actions == []
    assert len(incident.records) == 4


def test_lost_safety_power_control_keeps_failed_shutdown_unresolved():
    def execute(action):
        return SafetyPowerResult.FAILED

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        lost_capabilities={Capability.SAFETY_POWER_CONTROL},
        execute_action=execute,
    )

    assert incident.safety_power_control_lost
    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
    assert incident.session_state is SessionState.ABORTED


def test_unverified_shutdown_keeps_all_three_roles_unresolved():
    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.COMMANDED_UNVERIFIED,
    )

    assert len(incident.records) == 3
    assert len(incident.unresolved_actions) == 3
    assert incident.session_state is SessionState.ABORTED


def test_missing_accessories_result_remains_unresolved():
    from modules.guardian_types import SafetyPowerRole
    from modules.safety_power_manager import SafetyPowerRoleRecord

    def execute_batch(roles):
        assert set(roles) == {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
            SafetyPowerRole.ACCESSORIES,
        }
        return [
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.ASIAIR,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.MOUNT,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
        ]

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: (_ for _ in ()).throw(
            AssertionError(f"Unexpected per-action call: {action}")
        ),
        execute_safety_power=execute_batch,
    )

    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
    assert incident.session_state is SessionState.ABORTED


def test_retry_targets_only_failed_power_role():
    attempts = []

    def execute(action):
        attempts.append(action)
        if (
            action is ProtectionAction.SAFETY_POWER_OFF_MOUNT
            and attempts.count(action) == 1
        ):
            return SafetyPowerResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=execute,
    )

    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ]

    retry_records = incident.retry_unresolved(execute)

    assert [record.action for record in retry_records] == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ]
    assert incident.unresolved_actions == []
    assert len(incident.records) == 4


def test_successful_retry_never_clears_aborted_session():
    incident = initiate_protection(
        triggers={ProtectionTrigger.ASIAIR_LOST},
        execute_action=lambda action: SafetyPowerResult.FAILED,
    )

    assert len(incident.unresolved_actions) == 3

    incident.retry_unresolved(
        lambda action: SafetyPowerResult.VERIFIED_OFF
    )

    assert incident.unresolved_actions == []
    assert incident.session_state is SessionState.ABORTED
    assert len(incident.records) == 6


def test_protection_never_issues_independent_mount_commands():
    attempted = []

    def execute(action):
        attempted.append(action)
        assert action in {
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
        }
        return SafetyPowerResult.VERIFIED_OFF

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
    assert incident.session_state is SessionState.ABORTED
