"""Guardian 1.0 session-state orchestration."""

from collections.abc import Mapping
from dataclasses import dataclass

from modules.capability_model import installation_ready
from modules.commissioning import CommissioningStatus
from modules.core_state import (
    abort_active_session,
    evaluate_pre_imaging_state,
)
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SessionState,
)
from modules.protection_evaluator import evaluate_protection_triggers


@dataclass(frozen=True)
class SessionEvaluation:
    """Result of one Guardian session-state evaluation."""

    state: SessionState
    triggers: frozenset[ProtectionTrigger]


def evaluate_session(
    *,
    current_state: SessionState,
    armed: bool,
    roof_state: RoofState,
    asiair_state: AsiairState,
    commissioning: CommissioningStatus,
    configuration_fingerprint: str,
    capability_statuses: Mapping[Capability, CapabilityStatus],
    ups_low_battery: bool = False,
) -> SessionEvaluation:
    """Evaluate Guardian session state without executing protection actions."""

    if current_state is SessionState.ABORTED:
        return SessionEvaluation(
            state=SessionState.ABORTED,
            triggers=frozenset(),
        )

    if current_state is not SessionState.IMAGING_PERMITTED:
        ready = installation_ready(
            commissioning,
            configuration_fingerprint,
            capability_statuses,
        )

        state = evaluate_pre_imaging_state(
            armed=armed,
            roof_state=roof_state,
            asiair_state=asiair_state,
            installation_ready=ready,
        )

        return SessionEvaluation(
            state=state,
            triggers=frozenset(),
        )

    required_statuses = [
        capability_statuses.get(
            capability,
            CapabilityStatus.UNKNOWN,
        )
        for capability in (
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.SAFETY_POWER_CONTROL,
        )
    ]

    triggers = evaluate_protection_triggers(
        session_state=current_state,
        roof_state=roof_state,
        asiair_state=asiair_state,
        required_capability_statuses=required_statuses,
        ups_low_battery=ups_low_battery,
    )

    state = abort_active_session(
        current_state=current_state,
        protection_triggered=bool(triggers),
    )

    return SessionEvaluation(
        state=state,
        triggers=frozenset(triggers),
    )
