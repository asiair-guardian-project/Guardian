from datetime import datetime, timezone

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    evaluate_commissioning_evidence,
)
from modules.protection_logic_commissioning import (
    evaluate_protection_logic_commissioning,
)


def test_all_authoritative_protection_paths_verify():
    evidence = evaluate_protection_logic_commissioning(
        observed_at=datetime.now(timezone.utc),
    )

    assert evidence.check is CommissioningCheck.PROTECTION_LOGIC
    assert evidence.passed
    assert evidence.observations["roof_closed"] is True
    assert evidence.observations["asiair_lost"] is True
    assert evidence.observations["protection_capability_lost"] is True
    assert evidence.observations["post_abort_retry"] is True
    assert evidence.observations["scenario_count"] == 3
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


def test_failed_safety_power_action_retries_after_abort():
    from modules.guardian_types import (
        CapabilityStatus,
        ProtectionAction,
        RoofState,
        AsiairState,
        SafetyPowerResult,
        SafetyPowerRole,
        SessionState,
    )
    from modules.protection_coordinator import initiate_protection
    from modules.protection_evaluator import evaluate_protection_triggers
    from modules.safety_power_manager import SafetyPowerRoleRecord

    triggers = evaluate_protection_triggers(
        session_state=SessionState.IMAGING_PERMITTED,
        roof_state=RoofState.CLOSED,
        asiair_state=AsiairState.ONLINE,
        required_capability_statuses=[CapabilityStatus.AVAILABLE],
    )

    attempts = 0

    def safety_power(roles):
        nonlocal attempts
        attempts += 1

        return [
            SafetyPowerRoleRecord(
                role=role,
                endpoint=None,
                result=(
                    SafetyPowerResult.FAILED
                    if attempts == 1
                    and role is SafetyPowerRole.MOUNT
                    else SafetyPowerResult.VERIFIED_OFF
                ),
            )
            for role in roles
        ]

    incident = initiate_protection(
        triggers=triggers,
        execute_action=lambda action: None,
        execute_safety_power=safety_power,
    )

    assert incident.session_state is SessionState.ABORTED
    assert incident.unresolved_actions == [
        ProtectionAction.SAFETY_POWER_OFF_MOUNT
    ]

    retry_records = incident.retry_unresolved(
        execute_action=lambda action: None,
        execute_safety_power=safety_power,
    )

    assert len(retry_records) == 1
    assert (
        retry_records[0].action
        is ProtectionAction.SAFETY_POWER_OFF_MOUNT
    )
    assert (
        retry_records[0].result
        is SafetyPowerResult.VERIFIED_OFF
    )
    assert incident.unresolved_actions == []
    assert incident.session_state is SessionState.ABORTED
    assert attempts == 2
