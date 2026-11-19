"""Guardian 1.0 application composition root."""

from copy import deepcopy

from modules.capability_probe import CapabilityProbeResult
from modules.capability_probe_coordinator import apply_probe_results
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import Capability, SessionState
from modules.guardian_v1_execution import GuardianV1Execution
from modules.guardian_v1_mode import GuardianV1Mode
from modules.guardian_v1_recovery_store import RecoveryStateError
from modules.runtime_supervisor import RuntimeSupervisor


class GuardianV1Application:
    """
    Top-level composition object for the Guardian 1.0 runtime.

    Construction is always safe: Guardian 1.0 starts in monitor-only mode
    and no hardware executors are connected here.
    """

    def __init__(
        self,
        *,
        configured_capabilities: set[Capability],
        recovery_store=None,
        allow_restart_abort: bool = False,
    ) -> None:
        """Compose the application.

        allow_restart_abort is OFF by default, so a watch-only process (such
        as the deployed monitor) behaves exactly as before. An armed-capable
        launcher turns it on: if Guardian restarts while an armed session is
        on record, it then powers the rig off and latches ABORTED.
        """
        self.mode = GuardianV1Mode()
        self.capabilities = CapabilityRegistry(
            configured_capabilities=configured_capabilities,
        )
        self.supervisor = RuntimeSupervisor()
        self.recovery_store = recovery_store
        self.allow_restart_abort = allow_restart_abort
        self._restart_abort_enabled_hardware = False
        self._recovery_load_attempted = False
        self._recovery_load_failed = False

        if self.recovery_store is not None:
            self.load_recovery_state()




    def load_recovery_state(self) -> bool:
        """Restore Guardian 1.0 state without executing hardware actions.

        A failed read or validation latches a recovery block. Existing
        protection incidents are never cleared by a failed load.
        """
        if self.recovery_store is None:
            return False

        if self._recovery_load_attempted:
            raise RecoveryStateError(
                "Recovery state may only be loaded during startup."
            )

        self._recovery_load_attempted = True

        try:
            state = self.recovery_store.read()
            self.supervisor.restore_recovery_state(
                state,
                abort_on_armed_restart=self.allow_restart_abort,
            )
        except RecoveryStateError as error:
            self._recovery_load_failed = True
            self.supervisor.block_recovery(
                f"Recovery state unavailable or invalid: {error}"
            )
            return False

        return True

    def evaluate_runtime_cycle(
        self,
        *,
        armed,
        roof_state,
        asiair_state,
        commissioning,
        configuration_fingerprint,
        execute_action,
        execute_safety_power=None,
        capability_statuses_override=None,
        ups_low_battery=False,
    ):
        """Evaluate one runtime cycle through the hardware-execution gate."""

        if self.supervisor.restart_abort_pending:
            if execute_safety_power is None:
                # Never let a required abort quietly become a simulation.
                raise RuntimeError(
                    "Restart abort is pending but no safety-power executor "
                    "was supplied."
                )
            if self.mode.monitor_only:
                # Restart after an armed session: this process was explicitly
                # allowed to cut power, and only for this abort. Hardware
                # stays enabled while the incident is open so retries are
                # real, and is switched back off below once the operator has
                # released it.
                self.mode.enable_hardware_execution()
                self._restart_abort_enabled_hardware = True

        if (
            self._restart_abort_enabled_hardware
            and self.supervisor.incident is None
            and not self.supervisor.restart_abort_pending
        ):
            self.mode.disable_hardware_execution()
            self._restart_abort_enabled_hardware = False

        if self.recovery_store is not None and armed:
            if (
                self.supervisor.incident is None
                and not self.supervisor.recovery_blocked
                and self.supervisor.session_state
                    is not SessionState.IMAGING_PERMITTED
            ):
                # Write an interrupted-session marker before ARM can
                # transition into an imaging-permitted state.
                state = self.supervisor.export_recovery_state()
                state["session_state"] = SessionState.IMAGING_PERMITTED.name
                state["shutdown_clean"] = False

                try:
                    self.recovery_store.write(state)
                except RecoveryStateError as error:
                    self.supervisor.block_recovery(
                        f"Unable to persist ARM state: {error}"
                    )

        execution = GuardianV1Execution(
            mode=self.mode,
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
        )

        result = self.supervisor.evaluate(
            armed=armed,
            roof_state=roof_state,
            asiair_state=asiair_state,
            commissioning=commissioning,
            configuration_fingerprint=configuration_fingerprint,
            capability_statuses=(
                self.capabilities.snapshot()
                if capability_statuses_override is None
                else capability_statuses_override
            ),
            execute_action=execution.execute_action,
            execute_safety_power=execution.execute_safety_power,
            ups_low_battery=ups_low_battery,
        )

        # Persist the completed evaluation, including new incidents and
        # subsequent safety-power retry records. Do not interrupt protection
        # execution when durable storage is unavailable.
        if self.recovery_store is not None and (
            self.supervisor.incident is not None
            or (
                not self.supervisor.recovery_blocked
                and not self._recovery_load_failed
                and (not armed or self.supervisor.session_state is SessionState.IMAGING_PERMITTED)
            )
        ):
            try:
                self.recovery_store.write(self.supervisor.export_recovery_state())
            except RecoveryStateError as error:
                self.supervisor.block_recovery(
                    f"Unable to persist runtime state: {error}"
                )

        return result

    def _commit_operator_transition(self, method_name, **kwargs) -> bool:
        """Persist a proposed operator transition before making it effective.

        A failed write leaves the incident and acknowledgment intact and
        latches an ARM block. No hardware callbacks are involved.
        """
        if self.recovery_store is None:
            return getattr(self.supervisor, method_name)(**kwargs)

        proposed = deepcopy(self.supervisor)
        if not getattr(proposed, method_name)(**kwargs):
            return False

        try:
            self.recovery_store.write(proposed.export_recovery_state())
        except RecoveryStateError as error:
            self.supervisor.block_recovery(
                f"Unable to persist operator transition: {error}"
            )
            return False

        # Keep the existing supervisor object so other references remain valid.
        self.supervisor.__dict__.update(proposed.__dict__)
        if method_name == "clear_recovery_block":
            self._recovery_load_failed = False
        return True

    def acknowledge_abort(self) -> bool:
        """Durably acknowledge an incident without releasing its safety latch."""
        return self._commit_operator_transition("acknowledge_abort")

    def end_session(self) -> bool:
        """Durably end an established session at DISARM; never cuts or restores power.

        Saved before it takes effect, so a restart after DISARM is not mistaken for a
        restart while armed. A failed save leaves the session as it was and blocks ARM.
        """
        return self._commit_operator_transition("end_session")

    def release_blocker(self):
        """Why releasing the abort would be refused right now, or None. Read-only."""
        return self.supervisor.release_blocker()

    def authorize_new_session(self) -> bool:
        """Durably release a resolved incident; never ARM or power on."""
        return self._commit_operator_transition("authorize_new_session")

    def clear_recovery_block(self, *, operator_inspected: bool) -> bool:
        """Durably clear a non-incident recovery block after inspection."""
        return self._commit_operator_transition(
            "clear_recovery_block", operator_inspected=operator_inspected
        )

    def _persist_after_fault(self) -> None:
        """Best-effort durable write; never interrupts protection."""

        if self.recovery_store is None:
            return

        try:
            self.recovery_store.write(self.supervisor.export_recovery_state())
        except Exception as error:
            self.supervisor.block_recovery(
                f"Unable to persist protection incident: {error}"
            )

    def abort_for_internal_fault(
        self,
        *,
        armed,
        execute_action,
        execute_safety_power=None,
    ):
        """Cut power after an internal Guardian fault during an armed session.

        Goes through the same hardware-execution gate as any protection, so
        it only acts for real when hardware execution is enabled.
        """

        execution = GuardianV1Execution(
            mode=self.mode,
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
        )
        incident = self.supervisor.abort_for_internal_fault(
            armed=armed,
            execute_action=execution.execute_action,
            execute_safety_power=execution.execute_safety_power,
        )

        if incident is not None:
            self._persist_after_fault()

        return incident

    def retry_protection(self, *, execute_action, execute_safety_power=None):
        """Retry unresolved power-off for an open incident.

        Used while a fault keeps stopping normal cycles, which would
        otherwise also stop the retries those cycles perform.
        """

        incident = self.supervisor.incident

        if incident is None or not incident.unresolved_actions:
            return False

        execution = GuardianV1Execution(
            mode=self.mode,
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
        )
        incident.retry_unresolved(
            execution.execute_action,
            execute_safety_power=execution.execute_safety_power,
        )
        self._persist_after_fault()

        return True

    def evaluate_observation(
        self,
        *,
        armed,
        observation,
        commissioning,
        configuration_fingerprint,
        execute_action,
        execute_safety_power=None,
        capability_statuses_override=None,
    ):
        """Evaluate one normalized observation through the runtime gate."""

        return self.evaluate_runtime_cycle(
            armed=armed,
            roof_state=observation.roof_state,
            asiair_state=observation.asiair_state,
            commissioning=commissioning,
            configuration_fingerprint=configuration_fingerprint,
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
            capability_statuses_override=capability_statuses_override,
            ups_low_battery=getattr(observation, "ups_low_battery", False),
        )

    def run_probe_cycle(self, probes):
        """Run a collection of read-only capability probes."""

        results = []

        for probe in probes:
            results.extend(self.run_capability_probe(probe))

        return tuple(results)

    def run_capability_probe(self, probe):
        """Run one read-only probe and apply its result or results."""

        probe_results = probe()

        if isinstance(probe_results, CapabilityProbeResult):
            results = (probe_results,)
        else:
            results = tuple(probe_results)

        self.apply_capability_probe_results(results)

        return results

    def apply_capability_probe_results(
        self,
        results,
    ) -> None:
        """Apply validated probe results to the application registry."""

        apply_probe_results(
            registry=self.capabilities,
            results=results,
        )
