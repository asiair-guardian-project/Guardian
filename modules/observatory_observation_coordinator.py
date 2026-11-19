"""Guardian 1.0 observatory safety observation coordination."""

from dataclasses import dataclass
from datetime import datetime

from modules.capability_probe import CapabilityProbeResult
from modules.capability_probe_coordinator import apply_probe_results
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    RoofState,
)
from modules.observatory_safety import (
    ObservatorySafetyObservation,
    normalized_roof_state,
)


@dataclass(frozen=True)
class ObservatoryObservationResult:
    """Combined observatory capability and normalized roof state."""

    capability_status: CapabilityStatus
    roof_state: RoofState
    observation_accepted: bool


class ObservatoryObservationCoordinator:
    """Retain valid observatory observations and enforce freshness."""

    def __init__(self) -> None:
        self._last_observation: ObservatorySafetyObservation | None = None

    @property
    def last_observation(self) -> ObservatorySafetyObservation | None:
        return self._last_observation

    def process_probe(
        self,
        *,
        probe_result: CapabilityProbeResult[
            ObservatorySafetyObservation
        ],
        registry: CapabilityRegistry,
        now: datetime,
        max_age_seconds: float,
    ) -> ObservatoryObservationResult:
        """Apply capability health and derive current normalized roof state."""

        if (
            probe_result.capability
            is not Capability.OBSERVATORY_SAFETY_MONITORING
        ):
            raise ValueError(
                "probe result is not for observatory safety monitoring"
            )

        apply_probe_results(
            registry=registry,
            results=[probe_result],
        )

        accepted = (
            probe_result.status is CapabilityStatus.AVAILABLE
            and isinstance(
                probe_result.observation,
                ObservatorySafetyObservation,
            )
        )

        if accepted:
            self._last_observation = probe_result.observation

        if not accepted:
            # A failed probe cannot establish the current roof position.
            # Retain the last observation for diagnostics only.
            roof_state = RoofState.UNKNOWN
        else:
            roof_state = normalized_roof_state(
                self._last_observation,
                now=now,
                max_age_seconds=max_age_seconds,
            )

        return ObservatoryObservationResult(
            capability_status=probe_result.status,
            roof_state=roof_state,
            observation_accepted=accepted,
        )
