"""Guardian 1.0 protection execution state and result tracking.

This module records protection action outcomes and unresolved required Safety
Power actions. Hardware-specific execution is added through adapters later.
"""

from dataclasses import dataclass

from modules.guardian_types import (
    MountStopResult,
    ProtectionAction,
    SafetyPowerResult,
    SafetyPowerRole,
)


@dataclass(frozen=True)
class ProtectionActionRecord:
    """Recorded outcome of one protection action attempt."""

    action: ProtectionAction
    result: MountStopResult | SafetyPowerResult


def safety_power_action_resolved(record: ProtectionActionRecord) -> bool:
    """Return True when a required Safety Power action needs no retry."""

    if record.action not in (
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ):
        raise ValueError("record is not a Safety Power action")

    return record.result is SafetyPowerResult.VERIFIED_OFF


SAFETY_POWER_ACTION_ROLES = {
    ProtectionAction.SAFETY_POWER_OFF_ASIAIR: SafetyPowerRole.ASIAIR,
    ProtectionAction.SAFETY_POWER_OFF_MOUNT: SafetyPowerRole.MOUNT,
    ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES: SafetyPowerRole.ACCESSORIES,
}

SAFETY_POWER_ROLE_ACTIONS = {
    role: action
    for action, role in SAFETY_POWER_ACTION_ROLES.items()
}


def execute_safety_power_actions(
    *,
    actions: list[ProtectionAction],
    execute_safety_power,
) -> list[ProtectionActionRecord]:
    """Execute requested Safety Power actions as one logical-role batch."""

    roles = {
        SAFETY_POWER_ACTION_ROLES[action]
        for action in actions
        if action in SAFETY_POWER_ACTION_ROLES
    }

    if not roles:
        return []

    try:
        role_records = execute_safety_power(roles)
    except Exception:
        return [
            ProtectionActionRecord(
                action=action,
                result=SafetyPowerResult.FAILED,
            )
            for action in actions
            if action in SAFETY_POWER_ACTION_ROLES
        ]

    results_by_role = {
        record.role: record.result
        for record in role_records
    }

    return [
        ProtectionActionRecord(
            action=action,
            result=results_by_role.get(
                SAFETY_POWER_ACTION_ROLES[action],
                SafetyPowerResult.FAILED,
            ),
        )
        for action in actions
        if action in SAFETY_POWER_ACTION_ROLES
    ]


def execute_protection_plan(
    *,
    plan: list[ProtectionAction],
    execute_action,
    execute_safety_power=None,
) -> list[ProtectionActionRecord]:
    """Execute a protection plan and record every logical action outcome.

    Mount actions execute individually. When a Safety Power batch executor is
    supplied, required Safety Power actions execute as one logical-role batch
    so shared physical endpoints are deduplicated and dependency-safe ordering
    is preserved.

    Without a batch executor, every action follows the legacy per-action path.
    """

    records: list[ProtectionActionRecord] = []

    if execute_safety_power is None:
        for action in plan:
            try:
                result = execute_action(action)
            except Exception:
                if action in (
                    ProtectionAction.REQUEST_MOUNT_STOP,
                    ProtectionAction.VERIFY_MOUNT_STOP,
                ):
                    result = MountStopResult.FAILED
                else:
                    result = SafetyPowerResult.FAILED

            records.append(
                ProtectionActionRecord(
                    action=action,
                    result=result,
                )
            )

        return records

    safety_power_actions = [
        action
        for action in plan
        if action in SAFETY_POWER_ACTION_ROLES
    ]
    safety_power_executed = False

    for action in plan:
        if action in SAFETY_POWER_ACTION_ROLES:
            if safety_power_executed:
                continue

            safety_power_executed = True
            records.extend(
                execute_safety_power_actions(
                    actions=safety_power_actions,
                    execute_safety_power=execute_safety_power,
                )
            )
            continue

        try:
            result = execute_action(action)
        except Exception:
            result = MountStopResult.FAILED

        records.append(
            ProtectionActionRecord(
                action=action,
                result=result,
            )
        )

    return records


def unresolved_safety_power_actions(
    records: list[ProtectionActionRecord],
) -> list[ProtectionAction]:
    """Return required Safety Power actions whose latest result is unresolved."""

    required_actions = (
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    )

    latest_records: dict[ProtectionAction, ProtectionActionRecord] = {}

    for record in records:
        if record.action in required_actions:
            latest_records[record.action] = record

    return [
        action
        for action in required_actions
        if action not in latest_records
        or not safety_power_action_resolved(latest_records[action])
    ]


def retry_unresolved_safety_power(
    *,
    records: list[ProtectionActionRecord],
    execute_action,
) -> list[ProtectionActionRecord]:
    """Retry only unresolved required Safety Power actions.

    Returns the records from this retry attempt. Earlier records remain
    unchanged so higher-level orchestration can preserve complete history.
    """

    retry_actions = unresolved_safety_power_actions(records)

    if not retry_actions:
        return []

    return execute_protection_plan(
        plan=retry_actions,
        execute_action=execute_action,
    )
