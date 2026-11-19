"""Guardian 1.0 protection-logic commissioning."""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
)
from modules.guardian_types import (
    AsiairState,
    CapabilityStatus,
    ProtectionAction,
    ProtectionTrigger,
    RoofState,
    SafetyPowerResult,
    SafetyPowerRole,
    SessionState,
)
from modules.protection_coordinator import initiate_protection
from modules.protection_evaluator import evaluate_protection_triggers
from modules.safety_power_manager import SafetyPowerRoleRecord


@dataclass(frozen=True)
class ProtectionLogicScenario:
    name: str
    roof_state: RoofState
    asiair_state: AsiairState
    required_capability_statuses: tuple[CapabilityStatus, ...]
    expected_trigger: ProtectionTrigger


def _successful_safety_power(roles):
    return [
        SafetyPowerRoleRecord(
            role=role,
            endpoint=None,
            result=SafetyPowerResult.VERIFIED_OFF,
        )
        for role in roles
    ]


def _unused_mount_action(action):
    raise AssertionError(
        f"unexpected mount action during base protection commissioning: {action}"
    )


def _verify_post_abort_retry() -> bool:
    """Verify unresolved Safety Power retries after ABORTED is latched."""

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
        execute_action=_unused_mount_action,
        execute_safety_power=safety_power,
    )

    if (
        incident.session_state is not SessionState.ABORTED
        or incident.unresolved_actions
        != [ProtectionAction.SAFETY_POWER_OFF_MOUNT]
    ):
        return False

    retry_records = incident.retry_unresolved(
        execute_action=_unused_mount_action,
        execute_safety_power=safety_power,
    )

    return (
        attempts == 2
        and len(retry_records) == 1
        and retry_records[0].action
        is ProtectionAction.SAFETY_POWER_OFF_MOUNT
        and retry_records[0].result
        is SafetyPowerResult.VERIFIED_OFF
        and not incident.unresolved_actions
        and incident.session_state is SessionState.ABORTED
    )


def evaluate_protection_logic_commissioning(
    *,
    observed_at: datetime,
) -> CommissioningEvidence:
    """Exercise all authoritative trigger classes through the real pipeline."""

    scenarios = (
        ProtectionLogicScenario(
            name="roof_closed",
            roof_state=RoofState.CLOSED,
            asiair_state=AsiairState.ONLINE,
            required_capability_statuses=(CapabilityStatus.AVAILABLE,),
            expected_trigger=ProtectionTrigger.ROOF_CLOSED,
        ),
        ProtectionLogicScenario(
            name="asiair_lost",
            roof_state=RoofState.OPEN,
            asiair_state=AsiairState.LOST,
            required_capability_statuses=(CapabilityStatus.AVAILABLE,),
            expected_trigger=ProtectionTrigger.ASIAIR_LOST,
        ),
        ProtectionLogicScenario(
            name="protection_capability_lost",
            roof_state=RoofState.OPEN,
            asiair_state=AsiairState.ONLINE,
            required_capability_statuses=(CapabilityStatus.FAILED,),
            expected_trigger=ProtectionTrigger.PROTECTION_CAPABILITY_LOST,
        ),
    )

    scenario_results = {}

    required_actions = {
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    }

    for scenario in scenarios:
        triggers = evaluate_protection_triggers(
            session_state=SessionState.IMAGING_PERMITTED,
            roof_state=scenario.roof_state,
            asiair_state=scenario.asiair_state,
            required_capability_statuses=list(
                scenario.required_capability_statuses
            ),
        )

        incident = initiate_protection(
            triggers=triggers,
                    execute_action=_unused_mount_action,
            execute_safety_power=_successful_safety_power,
        )

        recorded_actions = {
            record.action
            for record in incident.records
        }

        scenario_passed = (
            scenario.expected_trigger in triggers
            and incident.session_state is SessionState.ABORTED
            and required_actions <= recorded_actions
            and not incident.unresolved_actions
        )

        scenario_results[scenario.name] = scenario_passed

    post_abort_retry = _verify_post_abort_retry()

    passed = (
        all(scenario_results.values())
        and post_abort_retry
    )

    summary = (
        "Protection triggers and post-abort retry behavior verified"
        if passed
        else "Protection logic commissioning was not fully verified"
    )

    details: Mapping[str, object] = {
        **scenario_results,
        "post_abort_retry": post_abort_retry,
        "scenario_count": len(scenarios),
    }

    return CommissioningEvidence(
        check=CommissioningCheck.PROTECTION_LOGIC,
        completed=True,
        passed=passed,
        observed_at=observed_at,
        summary=summary,
        observations=details,
    )
