"""Guardian 1.0 ASIAIR observation coordination."""

from dataclasses import dataclass

from modules.asiair_state import AsiairStateTracker
from modules.capability_probe import CapabilityProbeResult
from modules.capability_probe_coordinator import apply_probe_results
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
)


@dataclass(frozen=True)
class AsiairObservationResult:
    """Combined ASIAIR capability and session-state result."""

    capability_status: CapabilityStatus
    asiair_state: AsiairState
    observation_accepted: bool


def process_asiair_probe(
    *,
    probe_result: CapabilityProbeResult[bool],
    registry: CapabilityRegistry,
    tracker: AsiairStateTracker,
) -> AsiairObservationResult:
    """Apply one ASIAIR monitoring probe to capability and session state."""

    if probe_result.capability is not Capability.ASIAIR_MONITORING:
        raise ValueError("probe result is not for ASIAIR monitoring")

    apply_probe_results(
        registry=registry,
        results=[probe_result],
    )

    accepted = (
        probe_result.status is CapabilityStatus.AVAILABLE
        and isinstance(probe_result.observation, bool)
    )

    if accepted:
        tracker.observe(probe_result.observation)

    return AsiairObservationResult(
        capability_status=probe_result.status,
        asiair_state=tracker.state,
        observation_accepted=accepted,
    )
