"""Guardian 1.0 runtime observation model."""

from collections.abc import Iterable
from dataclasses import dataclass

from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    MountMotionState,
    RoofState,
)


@dataclass(frozen=True)
class GuardianV1Observation:
    """Read-only normalized observations for one Guardian runtime cycle."""

    roof_state: RoofState
    asiair_state: AsiairState
    mount_motion: MountMotionState
    # True only when a UPS is on battery and at/below the low threshold.
    ups_low_battery: bool = False


def mount_motion_from_probe_results(
    results: Iterable[CapabilityProbeResult],
) -> MountMotionState:
    """Extract validated mount motion from independent mount probe results."""

    motion_results = [
        result
        for result in results
        if result.capability is Capability.INDEPENDENT_MOUNT_MOTION
    ]

    if len(motion_results) > 1:
        raise ValueError("duplicate independent mount-motion probe results")

    if not motion_results:
        return MountMotionState.UNKNOWN

    result = motion_results[0]

    if (
        result.status is CapabilityStatus.AVAILABLE
        and isinstance(result.observation, MountMotionState)
    ):
        return result.observation

    return MountMotionState.UNKNOWN


def build_guardian_v1_observation(
    *,
    observatory,
    asiair,
    mount_probe_results: Iterable[CapabilityProbeResult],
    ups_low_battery: bool = False,
) -> GuardianV1Observation:
    """Build one normalized read-only Guardian runtime observation."""

    return GuardianV1Observation(
        roof_state=observatory.roof_state,
        asiair_state=asiair.asiair_state,
        mount_motion=mount_motion_from_probe_results(
            mount_probe_results
        ),
        ups_low_battery=ups_low_battery,
    )
