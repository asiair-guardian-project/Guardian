"""Guardian 1.0 core session-state evaluation.

This module determines pre-imaging session state from independent Guardian
facts. Active-session protection events are intentionally handled separately
so a safety failure cannot silently downgrade IMAGING_PERMITTED to a waiting
state.
"""

from modules.guardian_types import (
    AsiairState,
    RoofState,
    SessionState,
)


def evaluate_pre_imaging_state(
    *,
    armed: bool,
    roof_state: RoofState,
    asiair_state: AsiairState,
    installation_ready: bool,
) -> SessionState:
    """Return the appropriate state before active imaging is established."""

    if not armed:
        return SessionState.DISARMED

    if roof_state is not RoofState.OPEN:
        return SessionState.WAITING_FOR_ROOF

    if not installation_ready:
        return SessionState.WAITING_FOR_PROTECTION

    if asiair_state is not AsiairState.ONLINE:
        return SessionState.WAITING_FOR_PROTECTION

    return SessionState.IMAGING_PERMITTED


def abort_active_session(
    *,
    current_state: SessionState,
    protection_triggered: bool,
) -> SessionState:
    """Apply a protection-trigger transition to an established session.

    Once imaging has been permitted, a protection trigger latches the session
    ABORTED. An ABORTED session remains ABORTED until explicitly reset by
    higher-level session control.
    """

    if current_state is SessionState.ABORTED:
        return SessionState.ABORTED

    if (
        current_state is SessionState.IMAGING_PERMITTED
        and protection_triggered
    ):
        return SessionState.ABORTED

    return current_state
