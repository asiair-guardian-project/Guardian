from modules.asiair_observation_coordinator import AsiairObservationResult
from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    MountMotionState,
    RoofState,
)
from modules.guardian_v1_observation import (
    GuardianV1Observation,
    build_guardian_v1_observation,
    mount_motion_from_probe_results,
)
from modules.observatory_observation_coordinator import (
    ObservatoryObservationResult,
)


def test_guardian_v1_observation_snapshot():
    observation = GuardianV1Observation(
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        mount_motion=MountMotionState.STATIONARY,
    )

    assert observation.roof_state is RoofState.OPEN
    assert observation.asiair_state is AsiairState.ONLINE
    assert observation.mount_motion is MountMotionState.STATIONARY


def test_guardian_v1_observation_is_immutable():
    observation = GuardianV1Observation(
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        mount_motion=MountMotionState.STATIONARY,
    )

    try:
        observation.roof_state = RoofState.CLOSED
    except Exception:
        pass
    else:
        raise AssertionError("GuardianV1Observation must be immutable")


def test_mount_motion_from_successful_probe():
    results = [
        CapabilityProbeResult(
            capability=Capability.INDEPENDENT_MOUNT_MOTION,
            status=CapabilityStatus.AVAILABLE,
            observation=MountMotionState.MOVING,
            detail="motion observed",
        )
    ]

    assert (
        mount_motion_from_probe_results(results)
        is MountMotionState.MOVING
    )


def test_mount_motion_unknown_when_probe_not_available():
    results = [
        CapabilityProbeResult(
            capability=Capability.INDEPENDENT_MOUNT_MOTION,
            status=CapabilityStatus.UNKNOWN,
            observation=None,
            detail="mount communication unavailable",
        )
    ]

    assert (
        mount_motion_from_probe_results(results)
        is MountMotionState.UNKNOWN
    )


def test_mount_motion_rejects_duplicate_motion_results():
    results = [
        CapabilityProbeResult(
            capability=Capability.INDEPENDENT_MOUNT_MOTION,
            status=CapabilityStatus.AVAILABLE,
            observation=MountMotionState.MOVING,
            detail="first observation",
        ),
        CapabilityProbeResult(
            capability=Capability.INDEPENDENT_MOUNT_MOTION,
            status=CapabilityStatus.AVAILABLE,
            observation=MountMotionState.STATIONARY,
            detail="duplicate observation",
        ),
    ]

    try:
        mount_motion_from_probe_results(results)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "duplicate mount-motion probe results must be rejected"
        )


def test_build_guardian_v1_observation():
    roof = ObservatoryObservationResult(
        capability_status=CapabilityStatus.AVAILABLE,
        roof_state=RoofState.OPEN,
        observation_accepted=True,
    )

    asiair = AsiairObservationResult(
        capability_status=CapabilityStatus.AVAILABLE,
        asiair_state=AsiairState.ONLINE,
        observation_accepted=True,
    )

    mount_results = [
        CapabilityProbeResult(
            capability=Capability.INDEPENDENT_MOUNT_MOTION,
            status=CapabilityStatus.AVAILABLE,
            observation=MountMotionState.MOVING,
            detail="motion observed",
        )
    ]

    observation = build_guardian_v1_observation(
        observatory=roof,
        asiair=asiair,
        mount_probe_results=mount_results,
    )

    assert observation == GuardianV1Observation(
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        mount_motion=MountMotionState.MOVING,
    )


def test_build_observation_defaults_missing_mount_motion_to_unknown():
    roof = ObservatoryObservationResult(
        capability_status=CapabilityStatus.AVAILABLE,
        roof_state=RoofState.OPEN,
        observation_accepted=True,
    )

    asiair = AsiairObservationResult(
        capability_status=CapabilityStatus.AVAILABLE,
        asiair_state=AsiairState.ONLINE,
        observation_accepted=True,
    )

    observation = build_guardian_v1_observation(
        observatory=roof,
        asiair=asiair,
        mount_probe_results=[],
    )

    assert observation.mount_motion is MountMotionState.UNKNOWN
