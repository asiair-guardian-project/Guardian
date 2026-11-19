"""Guardian 1.0 runtime safety orchestration."""

from collections.abc import Mapping
from dataclasses import dataclass

from modules.commissioning import CommissioningStatus
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    RoofState,
    SessionState,
)
from modules.protection_coordinator import (
    ProtectionIncident,
    initiate_protection,
)
from modules.session_orchestrator import (
    SessionEvaluation,
    evaluate_session,
)


@dataclass(frozen=True)
class RuntimeEvaluation:
    """Result of one Guardian runtime evaluation cycle."""

    session: SessionEvaluation
    incident: ProtectionIncident | None


def evaluate_runtime(
    *,
    current_state: SessionState,
    armed: bool,
    roof_state: RoofState,
    asiair_state: AsiairState,
    commissioning: CommissioningStatus,
    configuration_fingerprint: str,
    capability_statuses: Mapping[Capability, CapabilityStatus],
    execute_action,
    execute_safety_power=None,
    ups_low_battery: bool = False,
) -> RuntimeEvaluation:
    """Evaluate session state and initiate protection when required."""

    session = evaluate_session(
        current_state=current_state,
        armed=armed,
        roof_state=roof_state,
        asiair_state=asiair_state,
        commissioning=commissioning,
        configuration_fingerprint=configuration_fingerprint,
        capability_statuses=capability_statuses,
        ups_low_battery=ups_low_battery,
    )

    if not session.triggers:
        return RuntimeEvaluation(
            session=session,
            incident=None,
        )

    required_capabilities = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
    }

    lost_capabilities = {
        capability
        for capability in required_capabilities
        if capability_statuses.get(
            capability,
            CapabilityStatus.UNKNOWN,
        )
        is not CapabilityStatus.AVAILABLE
    }

    incident = initiate_protection(
        triggers=set(session.triggers),
        lost_capabilities=lost_capabilities,
        execute_action=execute_action,
        execute_safety_power=execute_safety_power,
    )

    return RuntimeEvaluation(
        session=session,
        incident=incident,
    )
