"""Guardian 1.0 one-cycle shadow runtime composition."""

from dataclasses import dataclass, replace
from datetime import datetime

from modules.guardian_v1_observation import GuardianV1Observation
from modules.guardian_v1_roof_filter import GuardianV1RoofFilter, RoofFilterResult
from modules.guardian_types import Capability, CapabilityStatus, RoofState, SessionState
from modules.guardian_v1_observation_cycle import run_observation_cycle
from modules.ups_adapter import DEFAULT_UNREADABLE_GRACE_SECONDS, UpsReadTracker


@dataclass(frozen=True)
class GuardianV1ShadowCycleResult:
    """Result of one Guardian 1.0 shadow runtime cycle."""

    observation: GuardianV1Observation
    evaluation: object
    roof_filter: RoofFilterResult


class GuardianV1ShadowRuntime:
    """
    Compose one read-only observation cycle with Guardian runtime evaluation.

    Hardware execution remains governed by GuardianV1Application's mode gate.
    """

    def __init__(
        self,
        *,
        application,
        asiair_tracker,
        observatory_coordinator,
        asiair_adapter,
        observatory_adapter,
        safety_power_topology,
        safety_power_adapters,
        roof_max_age_seconds,
        commissioning,
        configuration_fingerprint,
        execute_action,
        execute_safety_power=None,
        ups_adapter=None,
        ups_low_battery_percent: int = 35,
        ups_unreadable_grace_seconds: float = DEFAULT_UNREADABLE_GRACE_SECONDS,
        safety_power_schedule=None,
    ) -> None:
        self._application = application
        self._roof_filter = GuardianV1RoofFilter()
        self._asiair_tracker = asiair_tracker
        self._observatory_coordinator = observatory_coordinator
        self._asiair_adapter = asiair_adapter
        self._observatory_adapter = observatory_adapter
        self._safety_power_topology = safety_power_topology
        self._safety_power_adapters = safety_power_adapters
        self._roof_max_age_seconds = roof_max_age_seconds
        self._commissioning = commissioning
        self._configuration_fingerprint = configuration_fingerprint
        self._execute_action = execute_action
        self._execute_safety_power = execute_safety_power
        self._ups_adapter = ups_adapter
        self._safety_power_schedule = safety_power_schedule
        self._ups_low_battery_percent = ups_low_battery_percent
        # One tracker for the life of the runtime, so it can time how long
        # the UPS has been unreadable across cycles.
        self._ups_tracker = (
            UpsReadTracker(ups_unreadable_grace_seconds)
            if ups_adapter is not None else None
        )

    def run_cycle(
        self,
        *,
        armed: bool,
        now: datetime,
    ) -> GuardianV1ShadowCycleResult:
        """Run one read-only observation and runtime-evaluation cycle."""

        cycle = run_observation_cycle(
            registry=self._application.capabilities,
            asiair_tracker=self._asiair_tracker,
            observatory_coordinator=self._observatory_coordinator,
            asiair_adapter=self._asiair_adapter,
            observatory_adapter=self._observatory_adapter,
            now=now,
            roof_max_age_seconds=self._roof_max_age_seconds,
            safety_power_topology=self._safety_power_topology,
            safety_power_adapters=self._safety_power_adapters,
            ups_adapter=self._ups_adapter,
            ups_low_battery_percent=self._ups_low_battery_percent,
            ups_tracker=self._ups_tracker,
            safety_power_schedule=self._safety_power_schedule,
        )

        roof_filter = self._roof_filter.evaluate(
            cycle.observation.roof_state,
            now=now,
        )

        effective_observation = replace(
            cycle.observation,
            roof_state=roof_filter.effective_state,
        )

        # Preserve actual probe results in the capability registry.
        # Only the active-session evaluation may temporarily tolerate
        # an UNKNOWN observatory reading.
        capability_override = None

        if (
            self._application.supervisor.session_state
            is SessionState.IMAGING_PERMITTED
            and cycle.observation.roof_state is RoofState.UNKNOWN
            and not roof_filter.timed_out
        ):
            capability_override = dict(
                self._application.capabilities.snapshot()
            )
            capability_override[
                Capability.OBSERVATORY_SAFETY_MONITORING
            ] = CapabilityStatus.AVAILABLE

        evaluation = self._application.evaluate_observation(
            armed=armed,
            observation=effective_observation,
            commissioning=self._commissioning,
            configuration_fingerprint=self._configuration_fingerprint,
            execute_action=self._execute_action,
            execute_safety_power=self._execute_safety_power,
            capability_statuses_override=capability_override,
        )

        return GuardianV1ShadowCycleResult(
            observation=cycle.observation,
            evaluation=evaluation,
            roof_filter=roof_filter,
        )
