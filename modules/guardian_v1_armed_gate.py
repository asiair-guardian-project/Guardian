"""Explicit, fail-closed ARM authority for an integrated Guardian runtime.

This component does not modify the deployed monitor service, operate outlets,
or enable hardware mode by itself. The owning runtime must call cycle().
"""
from datetime import datetime, timezone
import logging

from modules.guardian_types import SessionState

_logger = logging.getLogger("guardian_v1.armed_gate")


class GuardianV1ArmedGate:
    def __init__(self, *, application, observation_runtime, arm_blockers=()):
        if application.recovery_store is None:
            raise ValueError("Durable recovery store required")
        if application.mode.hardware_execution_enabled:
            raise RuntimeError("Gate must be constructed with hardware disabled")
        self.application = application
        self.observation_runtime = observation_runtime
        self._armed = False
        # Each blocker returns None, or a sentence saying why ARM must be refused
        # (for example "Guardian v0.6 is running"). A blocker that raises
        # refuses ARM: an unanswered safety question is never a yes.
        self._arm_blockers = tuple(arm_blockers)
        self.last_refusal = None

    @property
    def armed(self):
        return self._armed

    def arm(self):
        """Authorize ARM only after separately verified commissioning and operator consent.

        Does not switch hardware mode on; that is a distinct commissioning step.
        """
        reason = self.refusal_reason()
        self.last_refusal = reason
        if reason is not None:
            _logger.info("ARM refused: %s", reason)
            return False
        self._armed = True
        return True

    @staticmethod
    def _incident_refusal(supervisor):
        """Explain an open incident. Wording only: ARM is refused either way, and this never raises."""
        default = "A protection incident is open and must be acknowledged first"
        try:
            if not supervisor.abort_acknowledged:
                return default
            blocker = supervisor.release_blocker()
            if blocker is None:
                return "The abort is acknowledged; release it (ALLOW NEW SESSION) before ARM"
            return "The abort is acknowledged but cannot be released yet: " + blocker
        except Exception:
            return default

    def refusal_reason(self):
        """Why ARM would be refused right now, or None. Changes nothing."""
        if self._armed:
            return "Already armed"
        if self.application.mode.monitor_only:
            return "Hardware execution is disabled by the launch setting (monitor-only)"
        supervisor = self.application.supervisor
        if supervisor.incident is not None:
            return self._incident_refusal(supervisor)
        if supervisor.recovery_blocked:
            return "Recovery is blocked: " + (getattr(supervisor, "recovery_block_reason", None) or "unresolved")
        if supervisor.session_state is not SessionState.DISARMED:
            return f"Session is {supervisor.session_state.name}, not DISARMED"
        commissioning = self.observation_runtime._commissioning
        fingerprint = self.observation_runtime._configuration_fingerprint
        if not commissioning.valid_for_configuration(fingerprint):
            return "Commissioning is not valid for this configuration"
        for blocker in self._arm_blockers:
            try:
                reason = blocker()
            except Exception:
                reason = "An ARM safety check could not be completed"
            if reason:
                return str(reason)
        return None

    def disarm(self):
        """Revoke ARM and end an established session. Returns True if a session was ended.

        DISARM never clears an incident or changes hardware power. Without ending the
        session it would stay IMAGING_PERMITTED, ARM would be refused, and a restart
        would be treated as a restart while armed.
        """
        self._armed = False        # first, and unconditionally: nothing below may keep it armed
        try:
            return bool(self.application.end_session())
        except Exception:
            _logger.exception("DISARM could not end the session")
            return False

    def _protect_after_fault(self, was_armed):
        """An unexpected error escaped a cycle: protect the gear first.

        If Guardian was armed (or a session is active) the rig is powered off
        now, because Guardian can no longer vouch for its own protection. If
        an incident is already open, its unresolved power-off is retried,
        since the fault may be stopping the normal cycles that retry it.
        Nothing here may raise: the original error is re-raised afterwards.
        """
        application = self.application
        runtime = self.observation_runtime
        execute_action = getattr(runtime, "_execute_action", None)
        execute_safety_power = getattr(runtime, "_execute_safety_power", None)

        if execute_safety_power is None or application.mode.monitor_only:
            return

        try:
            if application.supervisor.incident is None:
                application.abort_for_internal_fault(
                    armed=was_armed,
                    execute_action=execute_action,
                    execute_safety_power=execute_safety_power,
                )
            else:
                application.retry_protection(
                    execute_action=execute_action,
                    execute_safety_power=execute_safety_power,
                )
        except Exception:
            _logger.exception("Fault protection could not complete")

    def cycle(self, *, now=None):
        """Run the existing observation + supervisor + execution path.

        If a hardware-enabled runtime loses its ARM authorization, refuse to
        silently run as a monitor; operator must explicitly recommission.
        """
        now = now or datetime.now(timezone.utc)
        if self._armed:
            if self.application.mode.monitor_only:
                self._armed = False
                raise RuntimeError("Hardware execution disabled while armed")
            commissioning = self.observation_runtime._commissioning
            fingerprint = self.observation_runtime._configuration_fingerprint
            if not commissioning.valid_for_configuration(fingerprint):
                self._armed = False
                # An already-latched incident must retain its shutdown retry
                # authority. Never silently turn its real retries into SIMULATED.
                if self.application.supervisor.incident is None:
                    self.application.mode.disable_hardware_execution()
                raise RuntimeError("Commissioning invalidated while armed")
        try:
            result = self.observation_runtime.run_cycle(armed=self._armed, now=now)
        except Exception:
            was_armed = self._armed
            self._armed = False
            self._protect_after_fault(was_armed)
            incident = self.application.supervisor.incident
            if incident is None:
                self.application.mode.disable_hardware_execution()
            else:
                # The evaluation may have latched an incident before a later
                # failure (including a failed persistence attempt). Keep real
                # power retries available and attempt a durable incident write.
                store = self.application.recovery_store
                try:
                    store.write(self.application.supervisor.export_recovery_state())
                except Exception as error:
                    self.application.supervisor.block_recovery(
                        f"Unable to persist protection incident: {error}"
                    )
            raise
        if self.application.supervisor.incident is not None:
            self._armed = False
        return result
