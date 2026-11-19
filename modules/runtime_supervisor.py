"""Guardian 1.0 persistent runtime supervision."""

from collections.abc import Mapping

from modules.commissioning import CommissioningStatus
from modules.guardian_runtime import RuntimeEvaluation, evaluate_runtime
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SessionState,
)
from modules.protection_coordinator import ProtectionIncident, initiate_protection

# Session states that mean "the operator had armed Guardian". DISARMED and
# ABORTED are deliberately absent: a disarmed Guardian promised nothing, and an
# ABORTED one already has an incident that is retried on its own.
_ARMED_SESSION_STATES = frozenset({
    SessionState.WAITING_FOR_ROOF,
    SessionState.WAITING_FOR_PROTECTION,
    SessionState.IMAGING_PERMITTED,
})

RESTART_RECOVERY_REASON = "Guardian restart requires operator recovery"


class RuntimeSupervisor:
    """Own persistent Guardian session and protection-incident state."""

    def __init__(self) -> None:
        self._session_state = SessionState.DISARMED
        self._incident: ProtectionIncident | None = None
        self._abort_acknowledged = False
        self._incident_history: list[ProtectionIncident] = []
        self._fresh_verification_required = False
        self._fresh_verified_actions = set()
        self._recovery_blocked = False
        self._recovery_block_reason: str | None = None
        self._restart_abort_pending = False

    @property
    def restart_abort_pending(self) -> bool:
        """Whether a restart found an armed session that must be aborted.

        Set only by restore_recovery_state(). Cleared when the abort runs.
        """
        return self._restart_abort_pending

    @property
    def recovery_blocked(self) -> bool:
        """Whether unresolved restart recovery prohibits ARM."""
        return self._recovery_blocked

    @property
    def recovery_block_reason(self) -> str | None:
        return self._recovery_block_reason

    def block_recovery(self, reason: str) -> None:
        """Latch a recovery block without changing protection records."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Recovery block requires a reason.")

        self._recovery_blocked = True
        self._recovery_block_reason = reason

    def clear_recovery_block(self, *, operator_inspected: bool) -> bool:
        """Clear a non-incident recovery block after explicit inspection.

        Never clears an active protection incident or arms equipment.
        """
        if not self._recovery_blocked:
            return False

        if self._incident is not None:
            return False

        if operator_inspected is not True:
            return False

        self._recovery_blocked = False
        self._recovery_block_reason = None
        self._session_state = SessionState.DISARMED
        return True

    @property
    def session_state(self) -> SessionState:
        return self._session_state

    @property
    def incident(self) -> ProtectionIncident | None:
        return self._incident

    def evaluate(
        self,
        *,
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
        """Run one persistent Guardian supervision cycle."""

        if self._incident is None and self._restart_abort_pending:
            # Guardian was armed when it stopped. Whatever happened in the
            # gap was unwatched, so power the rig off now (ASIAIR, mount,
            # accessories) and latch ABORTED. The recovery block set at
            # restore is converted into this incident, which carries the
            # same operator-acknowledgment requirement and can be released.
            self._restart_abort_pending = False
            incident = initiate_protection(
                triggers={ProtectionTrigger.RESTART_WHILE_ARMED},
                lost_capabilities=set(),
                execute_action=execute_action,
                execute_safety_power=execute_safety_power,
            )
            self._incident = incident
            self._session_state = SessionState.ABORTED
            if self._recovery_block_reason == RESTART_RECOVERY_REASON:
                self._recovery_blocked = False
                self._recovery_block_reason = None
            return RuntimeEvaluation(
                session=self._aborted_session_evaluation(),
                incident=incident,
            )

        if self._incident is not None:
            # An aborted session remains latched. Retry power shutdown only.
            # Never attempt mount STOP through the Wave Wi-Fi interface.
            self._incident.retry_unresolved(
                execute_action,
                execute_safety_power=execute_safety_power,
            )

            self._session_state = SessionState.ABORTED

            return RuntimeEvaluation(
                session=self._aborted_session_evaluation(),
                incident=self._incident,
            )

        if self._recovery_blocked:
            # Recovery uncertainty must never transition to imaging.
            self._session_state = SessionState.DISARMED
            return RuntimeEvaluation(
                session=self._blocked_session_evaluation(),
                incident=None,
            )

        result = evaluate_runtime(
            current_state=self._session_state,
            armed=armed,
            roof_state=roof_state,
            asiair_state=asiair_state,
            commissioning=commissioning,
            configuration_fingerprint=configuration_fingerprint,
            capability_statuses=capability_statuses,
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
            ups_low_battery=ups_low_battery,
        )

        self._session_state = result.session.state

        if result.incident is not None:
            self._incident = result.incident
            self._session_state = SessionState.ABORTED

        return result

    def abort_for_internal_fault(
        self,
        *,
        armed: bool,
        execute_action,
        execute_safety_power=None,
    ) -> ProtectionIncident | None:
        """Power the rig off because Guardian itself failed mid-session.

        Acts only when the operator had armed Guardian or a session is active
        (IMAGING_PERMITTED) and no incident exists yet. A fault in a Guardian
        that is not protecting anything does not cut power. Returns the new
        incident, or None when nothing was done.
        """

        if self._incident is not None:
            return None

        if not armed and self._session_state is not SessionState.IMAGING_PERMITTED:
            return None

        incident = initiate_protection(
            triggers={ProtectionTrigger.INTERNAL_FAULT},
            lost_capabilities=set(),
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
        )
        self._incident = incident
        self._session_state = SessionState.ABORTED

        return incident

    def end_session(self) -> bool:
        """The operator ended the session (DISARM): IMAGING_PERMITTED returns to DISARMED.

        Only an established session needs this: earlier states follow the armed flag by
        themselves. Never touches an open incident (it stays latched, and releasing it is
        a separate acknowledged step), never switches power, and never ARMs. Returns True
        only when the state actually changed.
        """
        if self._incident is not None:
            return False
        if self._session_state is not SessionState.IMAGING_PERMITTED:
            return False
        self._session_state = SessionState.DISARMED
        return True

    @property
    def abort_acknowledged(self) -> bool:
        """Whether the operator has acknowledged the current abort."""
        return self._abort_acknowledged

    def acknowledge_abort(self) -> bool:
        """Acknowledge an abort without clearing its safety latch.

        This operation never authorizes imaging, clears an incident,
        stops unresolved protection retries, or controls hardware.
        """
        if self._incident is None:
            return False

        self._abort_acknowledged = True
        return True

    @property
    def incident_history(self) -> tuple[ProtectionIncident, ...]:
        """Completed incidents retained for operator review."""
        return tuple(self._incident_history)

    def release_blocker(self) -> str | None:
        """Why authorize_new_session() would refuse right now, or None. Changes nothing.

        Mirrors authorize_new_session() exactly; a test asserts the two never disagree.
        """
        if self._incident is None:
            return "There is no active incident"

        if not self._abort_acknowledged:
            return "The abort has not been acknowledged yet"

        if self._incident.unresolved_actions:
            return "Power-off actions are still unresolved"

        if self._recovery_blocked and not self._fresh_verification_required:
            return "Recovery is blocked: " + (self._recovery_block_reason or "unresolved")

        if self._fresh_verification_required:
            from modules.protection_planner import build_protection_plan

            if self._fresh_verified_actions != set(build_protection_plan()):
                return "Fresh verification that the equipment is off is still incomplete"

        return None

    def authorize_new_session(self) -> bool:
        """Release a resolved, acknowledged abort to DISARMED.

        The caller must separately obtain explicit operator authorization
        after inspection. This method never arms or powers on equipment.
        """
        if self._incident is None:
            return False

        if not self._abort_acknowledged:
            return False

        if self._incident.unresolved_actions:
            return False

        # A storage/unknown-state block cannot be bypassed merely by ACK.
        if self._recovery_blocked and not self._fresh_verification_required:
            return False

        if self._fresh_verification_required:
            from modules.protection_planner import build_protection_plan

            if self._fresh_verified_actions != set(build_protection_plan()):
                return False

        self._incident_history.append(self._incident)
        self._incident = None
        self._abort_acknowledged = False
        self._fresh_verification_required = False
        self._fresh_verified_actions.clear()
        self._recovery_blocked = False
        self._recovery_block_reason = None
        self._session_state = SessionState.DISARMED
        return True

    def export_recovery_state(self) -> dict:
        """Return a strictly validated, serializable recovery snapshot."""
        from modules.guardian_v1_incident_codec import encode_incident
        from modules.guardian_v1_recovery_store import validate_recovery_state

        state = {
            "schema_version": 2,
            "active_incident": (
                encode_incident(self._incident)
                if self._incident is not None
                else None
            ),
            "abort_acknowledged": self._abort_acknowledged,
            "incident_history": [
                encode_incident(incident)
                for incident in self._incident_history
            ],
            "session_state": self._session_state.name,
            "shutdown_clean": False,
            "recovery_required": (
                self._incident is not None or self._recovery_blocked
            ),
        }
        return validate_recovery_state(state)

    def restore_recovery_state(
        self,
        state: dict,
        *,
        abort_on_armed_restart: bool = False,
    ) -> None:
        """Restore a persisted state without trusting old verification.

        With abort_on_armed_restart=True, a restart that finds a recorded
        armed session schedules a protective power-off (see evaluate()).
        """
        from modules.guardian_v1_incident_codec import decode_incident
        from modules.guardian_v1_recovery_store import validate_recovery_state

        validated = validate_recovery_state(state)

        incident = (
            decode_incident(validated["active_incident"])
            if validated["active_incident"] is not None
            else None
        )
        history = [
            decode_incident(item)
            for item in validated["incident_history"]
        ]

        saved_session = SessionState[validated["session_state"]]
        interrupted_session = (
            not validated["shutdown_clean"]
            and saved_session is not SessionState.DISARMED
        )
        recovery_blocked = (
            validated["recovery_required"] or interrupted_session
        )

        # Complete validation and decoding before mutating live state.
        self._incident = incident
        self._incident_history = history
        self._abort_acknowledged = validated["abort_acknowledged"]
        self._session_state = (
            SessionState.ABORTED
            if incident is not None
            else SessionState.DISARMED
        )

        self._recovery_blocked = recovery_blocked
        self._recovery_block_reason = (
            RESTART_RECOVERY_REASON
            if recovery_blocked
            else None
        )

        # An interrupted session that was armed (and has no incident yet)
        # needs a protective abort, but only when the caller has said this
        # process is allowed to cut power. Default is today's behaviour:
        # a recovery block that the operator inspects and clears.
        self._restart_abort_pending = (
            abort_on_armed_restart
            and interrupted_session
            and incident is None
            and saved_session in _ARMED_SESSION_STATES
        )

        self._fresh_verification_required = incident is not None
        self._fresh_verified_actions.clear()

    def record_fresh_power_verification(self, action, result) -> bool:
        """Record a new, externally obtained verification result.

        This method does not contact equipment. The eventual hardware
        adapter must supply genuine current-state evidence.
        """
        from modules.guardian_types import SafetyPowerResult
        from modules.protection_planner import build_protection_plan

        if self._incident is None or not self._fresh_verification_required:
            return False

        if action not in build_protection_plan():
            return False

        if result is SafetyPowerResult.VERIFIED_OFF:
            self._fresh_verified_actions.add(action)
        else:
            self._fresh_verified_actions.discard(action)

        return True

    def reset_aborted_session(self) -> bool:
        """Deprecated: aborts require explicit new-session authorization."""
        return False

    def _blocked_session_evaluation(self):
        from modules.session_orchestrator import SessionEvaluation

        return SessionEvaluation(
            state=SessionState.DISARMED,
            triggers=frozenset(),
        )

    def _aborted_session_evaluation(self):
        from modules.session_orchestrator import SessionEvaluation

        return SessionEvaluation(
            state=SessionState.ABORTED,
            triggers=frozenset(),
        )
