"""Guardian 1.0 read-only observation-cycle coordination."""

from dataclasses import dataclass
from datetime import datetime

from modules.asiair_capability_probe import probe_asiair_monitoring
from modules.asiair_observation_coordinator import process_asiair_probe
from modules.asiair_state import AsiairStateTracker
from modules.capability_probe_coordinator import apply_probe_results
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import CapabilityStatus
from modules.guardian_v1_observation import (
    GuardianV1Observation,
    build_guardian_v1_observation,
)
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.observatory_safety_capability_probe import (
    probe_observatory_safety,
)
from modules.safety_power_capability_probe import (
    probe_safety_power_control,
)
from modules.ups_adapter import (
    DEFAULT_LOW_BATTERY_PERCENT,
    read_ups_low_battery,
)


@dataclass(frozen=True)
class GuardianV1ObservationCycleResult:
    """Result of one read-only Guardian observation cycle."""

    observation: GuardianV1Observation


def run_observation_cycle(
    *,
    registry: CapabilityRegistry,
    asiair_tracker: AsiairStateTracker,
    observatory_coordinator: ObservatoryObservationCoordinator,
    asiair_adapter,
    observatory_adapter,
    now: datetime,
    roof_max_age_seconds: float,
    safety_power_topology=None,
    safety_power_adapters=None,
    ups_adapter=None,
    ups_low_battery_percent: int = DEFAULT_LOW_BATTERY_PERCENT,
    ups_tracker=None,
    safety_power_schedule=None,
) -> GuardianV1ObservationCycleResult:
    """Run one read-only observation cycle and normalize its observations."""

    asiair_probe = probe_asiair_monitoring(asiair_adapter)
    asiair_result = process_asiair_probe(
        probe_result=asiair_probe,
        registry=registry,
        tracker=asiair_tracker,
    )

    observatory_probe = probe_observatory_safety(observatory_adapter)

    observatory_now = now
    if (
        observatory_probe.status is CapabilityStatus.AVAILABLE
        and isinstance(
            observatory_probe.observation,
            ObservatorySafetyObservation,
        )
        and observatory_probe.observation.observed_at > observatory_now
    ):
        observatory_now = observatory_probe.observation.observed_at

    observatory_result = observatory_coordinator.process_probe(
        probe_result=observatory_probe,
        registry=registry,
        now=observatory_now,
        max_age_seconds=roof_max_age_seconds,
    )

    # Wave 150i Wi-Fi cannot provide reliable independent control
    # while ASIAIR owns the USB connection. Do not probe the mount.
    # Emergency protection is independent of mount motion.
    mount_probe_results = []

    if (
        safety_power_topology is not None
        and safety_power_adapters is not None
    ):
        def probe_strip():
            return probe_safety_power_control(
                topology=safety_power_topology,
                adapters=safety_power_adapters,
            )

        if safety_power_schedule is None:
            safety_power_probe = probe_strip()
        else:
            safety_power_probe = safety_power_schedule.run(probe_strip)

        if safety_power_probe is not None:
            apply_probe_results(
                registry=registry,
                results=[safety_power_probe],
            )

    observation = build_guardian_v1_observation(
        observatory=observatory_result,
        asiair=asiair_result,
        mount_probe_results=mount_probe_results,
        ups_low_battery=read_ups_low_battery(
            ups_adapter, ups_low_battery_percent, ups_tracker
        ),
    )

    return GuardianV1ObservationCycleResult(
        observation=observation,
    )
