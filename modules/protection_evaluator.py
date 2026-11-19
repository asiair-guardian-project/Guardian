"""Guardian 1.0 protection-trigger evaluation.

This module determines which protection triggers are present from normalized
Guardian state. It performs no hardware actions.
"""

from modules.guardian_types import (
    AsiairState,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SessionState,
)


def evaluate_protection_triggers(
    *,
    session_state: SessionState,
    roof_state: RoofState,
    asiair_state: AsiairState,
    required_capability_statuses: list[CapabilityStatus],
    ups_low_battery: bool = False,
) -> set[ProtectionTrigger]:
    """Return protection triggers present during active imaging.

    Protection triggers are evaluated only after imaging has been permitted.
    ABORTED sessions are handled by the retry/protection machinery rather than
    by generating new initial triggers here.
    """

    if session_state is not SessionState.IMAGING_PERMITTED:
        return set()

    triggers: set[ProtectionTrigger] = set()

    if roof_state is RoofState.CLOSED:
        triggers.add(ProtectionTrigger.ROOF_CLOSED)

    if asiair_state is AsiairState.LOST:
        triggers.add(ProtectionTrigger.ASIAIR_LOST)

    if any(
        status is not CapabilityStatus.AVAILABLE
        for status in required_capability_statuses
    ):
        triggers.add(ProtectionTrigger.PROTECTION_CAPABILITY_LOST)

    if ups_low_battery:
        triggers.add(ProtectionTrigger.UPS_LOW_BATTERY)

    return triggers
