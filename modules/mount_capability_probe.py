"""Guardian 1.0 independent mount capability probing."""

from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    MountMotionState,
)


def probe_mount_capabilities(adapter):
    """
    Non-destructively probe an independent mount adapter.

    A successful motion query establishes that the adapter's independent
    communication path is currently healthy. Capabilities declared by the
    commissioned adapter are therefore available through that path.

    This probe never requests STOP, verifies STOP, or invokes connection
    recovery.
    """

    capabilities = adapter.capabilities

    try:
        motion = adapter.query_motion()
    except Exception as exc:
        return [
            CapabilityProbeResult(
                capability=capability,
                status=CapabilityStatus.UNKNOWN,
                observation=None,
                detail=str(exc),
            )
            for capability in capabilities
        ]

    path_available = motion in (
        MountMotionState.MOVING,
        MountMotionState.STATIONARY,
    )

    status = (
        CapabilityStatus.AVAILABLE
        if path_available
        else CapabilityStatus.UNKNOWN
    )

    return [
        CapabilityProbeResult(
            capability=capability,
            status=status,
            observation=(
                motion
                if capability is Capability.INDEPENDENT_MOUNT_MOTION
                else None
            ),
            detail=(
                "independent mount communication path is available"
                if path_available
                else "independent mount communication path is not established"
            ),
        )
        for capability in capabilities
    ]
