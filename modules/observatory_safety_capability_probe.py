"""Guardian 1.0 observatory safety capability probe."""

from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import Capability, CapabilityStatus
from modules.observatory_safety import (
    ObservatorySafetyAdapter,
    ObservatorySafetyObservation,
)


def probe_observatory_safety(
    adapter: ObservatorySafetyAdapter,
) -> CapabilityProbeResult[ObservatorySafetyObservation]:
    """Probe observatory monitoring health separately from roof state."""

    try:
        observation = adapter.observe()
    except Exception as exc:
        return CapabilityProbeResult(
            capability=Capability.OBSERVATORY_SAFETY_MONITORING,
            status=CapabilityStatus.UNKNOWN,
            observation=None,
            detail=str(exc),
        )

    return CapabilityProbeResult(
        capability=Capability.OBSERVATORY_SAFETY_MONITORING,
        status=CapabilityStatus.AVAILABLE,
        observation=observation,
        detail=f"observatory safety state: {observation.state.name}",
    )
