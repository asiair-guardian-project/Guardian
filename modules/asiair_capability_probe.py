"""Guardian 1.0 ASIAIR monitoring capability probe."""

from modules.asiair_adapter import AsiairMonitorAdapter
from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import Capability, CapabilityStatus


def probe_asiair_monitoring(
    adapter: AsiairMonitorAdapter,
) -> CapabilityProbeResult[bool]:
    """Probe ASIAIR monitoring-path health and reachability separately."""

    try:
        reachable = adapter.is_reachable()
    except Exception as exc:
        return CapabilityProbeResult(
            capability=Capability.ASIAIR_MONITORING,
            status=CapabilityStatus.UNKNOWN,
            observation=None,
            detail=str(exc),
        )

    return CapabilityProbeResult(
        capability=Capability.ASIAIR_MONITORING,
        status=CapabilityStatus.AVAILABLE,
        observation=reachable,
        detail=(
            "ASIAIR reachable"
            if reachable
            else "ASIAIR unreachable"
        ),
    )
