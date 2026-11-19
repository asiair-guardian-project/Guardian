import pytest

from modules.guardian_types import (
    MountStopResult,
    ProtectionAction,
    SafetyPowerResult,
)
from modules.protection_execution import (
    ProtectionActionRecord,
    safety_power_action_resolved,
)


def test_verified_off_is_resolved():
    record = ProtectionActionRecord(
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        SafetyPowerResult.VERIFIED_OFF,
    )
    assert safety_power_action_resolved(record) is True


def test_commanded_unverified_remains_unresolved():
    record = ProtectionActionRecord(
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        SafetyPowerResult.COMMANDED_UNVERIFIED,
    )
    assert safety_power_action_resolved(record) is False
    assert record.result is not SafetyPowerResult.VERIFIED_OFF


def test_failed_safety_power_action_is_unresolved():
    record = ProtectionActionRecord(
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        SafetyPowerResult.FAILED,
    )
    assert safety_power_action_resolved(record) is False


def test_mount_stop_record_is_not_safety_power_result():
    record = ProtectionActionRecord(
        ProtectionAction.REQUEST_MOUNT_STOP,
        MountStopResult.SUCCEEDED,
    )

    with pytest.raises(ValueError):
        safety_power_action_resolved(record)


def test_stop_failure_does_not_block_safety_power_actions():
    from modules.protection_execution import execute_protection_plan

    plan = [
        ProtectionAction.REQUEST_MOUNT_STOP,
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ]

    def fake_execute(action):
        if action is ProtectionAction.REQUEST_MOUNT_STOP:
            return MountStopResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    records = execute_protection_plan(
        plan=plan,
        execute_action=fake_execute,
    )

    assert [record.action for record in records] == plan
    assert records[0].result is MountStopResult.FAILED
    assert records[1].result is SafetyPowerResult.VERIFIED_OFF
    assert records[2].result is SafetyPowerResult.VERIFIED_OFF


def test_asiair_power_failure_does_not_block_mount_power_off():
    from modules.protection_execution import execute_protection_plan

    plan = [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ]

    def fake_execute(action):
        if action is ProtectionAction.SAFETY_POWER_OFF_ASIAIR:
            return SafetyPowerResult.FAILED
        return SafetyPowerResult.VERIFIED_OFF

    records = execute_protection_plan(
        plan=plan,
        execute_action=fake_execute,
    )

    assert len(records) == 2
    assert records[0].result is SafetyPowerResult.FAILED
    assert records[1].result is SafetyPowerResult.VERIFIED_OFF


def test_exception_does_not_stop_later_actions():
    from modules.protection_execution import execute_protection_plan

    attempted = []

    plan = [
        ProtectionAction.REQUEST_MOUNT_STOP,
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ]

    def fake_execute(action):
        attempted.append(action)

        if action is ProtectionAction.REQUEST_MOUNT_STOP:
            raise RuntimeError("simulated STOP failure")

        return SafetyPowerResult.VERIFIED_OFF

    records = execute_protection_plan(
        plan=plan,
        execute_action=fake_execute,
    )

    assert attempted == plan
    assert records[0].result is MountStopResult.FAILED


def test_only_failed_safety_power_actions_are_unresolved():
    from modules.protection_execution import unresolved_safety_power_actions

    records = [
        ProtectionActionRecord(
            ProtectionAction.REQUEST_MOUNT_STOP,
            MountStopResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    assert unresolved_safety_power_actions(records) == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    ]


def test_commanded_unverified_is_retried():
    from modules.protection_execution import unresolved_safety_power_actions

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.COMMANDED_UNVERIFIED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    assert unresolved_safety_power_actions(records) == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
    ]


def test_retry_repeats_only_failed_asiair_power_action():
    from modules.protection_execution import retry_unresolved_safety_power

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    attempted = []

    def fake_execute(action):
        attempted.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    retry_records = retry_unresolved_safety_power(
        records=records,
        execute_action=fake_execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    ]
    assert retry_records[0].result is SafetyPowerResult.VERIFIED_OFF


def test_retry_repeats_both_failed_power_actions():
    from modules.protection_execution import retry_unresolved_safety_power

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    attempted = []

    def fake_execute(action):
        attempted.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    retry_unresolved_safety_power(
        records=records,
        execute_action=fake_execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
    ]


def test_retry_targets_only_unverified_power_action():
    from modules.protection_execution import retry_unresolved_safety_power

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.COMMANDED_UNVERIFIED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    attempted = []

    def fake_execute(action):
        attempted.append(action)
        return SafetyPowerResult.VERIFIED_OFF

    retry_records = retry_unresolved_safety_power(
        records=records,
        execute_action=fake_execute,
    )

    assert attempted == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
    ]
    assert len(retry_records) == 1
    assert retry_records[0].action is ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    assert retry_records[0].result is SafetyPowerResult.VERIFIED_OFF


def test_failed_retry_remains_unresolved():
    from modules.protection_execution import (
        retry_unresolved_safety_power,
        unresolved_safety_power_actions,
    )

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    def fake_execute(action):
        return SafetyPowerResult.FAILED

    retry_records = retry_unresolved_safety_power(
        records=records,
        execute_action=fake_execute,
    )

    assert unresolved_safety_power_actions(records + retry_records) == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    ]


def test_successful_later_retry_clears_unresolved_action():
    from modules.protection_execution import (
        retry_unresolved_safety_power,
        unresolved_safety_power_actions,
    )

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.FAILED,
        )
    ]

    def fail_again(action):
        return SafetyPowerResult.FAILED

    first_retry = retry_unresolved_safety_power(
        records=records,
        execute_action=fail_again,
    )

    def succeed(action):
        return SafetyPowerResult.VERIFIED_OFF

    second_retry = retry_unresolved_safety_power(
        records=first_retry,
        execute_action=succeed,
    )

    assert unresolved_safety_power_actions(second_retry) == []


def test_latest_success_resolves_earlier_failed_power_action():
    from modules.protection_execution import unresolved_safety_power_actions

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.FAILED,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    assert unresolved_safety_power_actions(records) == []


def test_execute_safety_power_actions_batches_required_roles():
    from modules.guardian_types import SafetyPowerRole
    from modules.protection_execution import execute_safety_power_actions
    from modules.safety_power_manager import SafetyPowerRoleRecord

    calls = []

    def execute_safety_power(roles):
        calls.append(set(roles))
        return [
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.ASIAIR,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.MOUNT,
                endpoint=None,
                result=SafetyPowerResult.COMMANDED_UNVERIFIED,
            ),
        ]

    records = execute_safety_power_actions(
        actions=[
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ],
        execute_safety_power=execute_safety_power,
    )

    assert calls == [{
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
    }]

    results = {
        record.action: record.result
        for record in records
    }

    assert (
        results[ProtectionAction.SAFETY_POWER_OFF_ASIAIR]
        is SafetyPowerResult.VERIFIED_OFF
    )
    assert (
        results[ProtectionAction.SAFETY_POWER_OFF_MOUNT]
        is SafetyPowerResult.COMMANDED_UNVERIFIED
    )


def test_execute_safety_power_actions_missing_role_result_fails():
    from modules.guardian_types import SafetyPowerRole
    from modules.protection_execution import execute_safety_power_actions
    from modules.safety_power_manager import SafetyPowerRoleRecord

    def execute_safety_power(roles):
        return [
            SafetyPowerRoleRecord(
                role=SafetyPowerRole.ASIAIR,
                endpoint=None,
                result=SafetyPowerResult.VERIFIED_OFF,
            ),
        ]

    records = execute_safety_power_actions(
        actions=[
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ],
        execute_safety_power=execute_safety_power,
    )

    results = {
        record.action: record.result
        for record in records
    }

    assert (
        results[ProtectionAction.SAFETY_POWER_OFF_ASIAIR]
        is SafetyPowerResult.VERIFIED_OFF
    )
    assert (
        results[ProtectionAction.SAFETY_POWER_OFF_MOUNT]
        is SafetyPowerResult.FAILED
    )


def test_execute_safety_power_actions_batch_exception_fails_all_roles():
    from modules.protection_execution import execute_safety_power_actions

    def execute_safety_power(roles):
        raise RuntimeError("Safety Power batch failed")

    records = execute_safety_power_actions(
        actions=[
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ],
        execute_safety_power=execute_safety_power,
    )

    assert [record.result for record in records] == [
        SafetyPowerResult.FAILED,
        SafetyPowerResult.FAILED,
    ]


def test_missing_accessories_shutdown_record_remains_unresolved():
    """A missing Pegasus result must not silently resolve shutdown."""
    from modules.protection_execution import unresolved_safety_power_actions

    records = [
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
            SafetyPowerResult.VERIFIED_OFF,
        ),
        ProtectionActionRecord(
            ProtectionAction.SAFETY_POWER_OFF_MOUNT,
            SafetyPowerResult.VERIFIED_OFF,
        ),
    ]

    assert unresolved_safety_power_actions(records) == [
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
