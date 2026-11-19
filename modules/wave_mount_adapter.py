"""Guardian 1.0 independent mount adapter for Sky-Watcher Wave mounts."""

import time
from collections.abc import Callable

from modules.guardian_types import (
    Capability,
    MountMotionState,
    MountStopResult,
)
from modules.wave_interface import (
    WaveCommunicationError,
    WaveInterface,
)
from modules.wave_position_sampler import (
    WavePositionSamplerError,
    decode_position,
)


class WaveMountAdapter:
    """Guardian mount adapter using an independent Wave communication path."""

    capabilities = frozenset(
        {
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    def __init__(
        self,
        *,
        wave: WaveInterface,
        recovery: Callable[[], bool],
        sample_interval_seconds: float = 2,
    ):
        self.wave = wave
        self.recovery = recovery
        self.sample_interval_seconds = sample_interval_seconds

    def _sample_motion(self) -> MountMotionState:
        try:
            axis1_before = decode_position(
                self.wave.get_position(1)
            )
            axis2_before = decode_position(
                self.wave.get_position(2)
            )

            time.sleep(self.sample_interval_seconds)

            axis1_after = decode_position(
                self.wave.get_position(1)
            )
            axis2_after = decode_position(
                self.wave.get_position(2)
            )

        except (WaveCommunicationError, WavePositionSamplerError):
            # Communication or response-decoding failure means this
            # configured capability cannot currently determine motion.
            return MountMotionState.UNKNOWN

        if (
            axis1_before != axis1_after
            or axis2_before != axis2_after
        ):
            return MountMotionState.MOVING

        return MountMotionState.STATIONARY

    def query_motion(self) -> MountMotionState:
        """Independently determine whether either Wave axis is moving."""

        return self._sample_motion()

    def request_stop(self) -> MountStopResult:
        """Request STOP independently on both Wave axes."""

        failed = False

        for axis in (1, 2):
            try:
                self.wave.stop(axis)
            except WaveCommunicationError:
                failed = True

        if failed:
            return MountStopResult.FAILED

        return MountStopResult.SUCCEEDED

    def verify_stop(self) -> MountStopResult:
        """Independently verify that both Wave axes remain stationary."""

        motion = self._sample_motion()

        if motion is MountMotionState.STATIONARY:
            return MountStopResult.SUCCEEDED

        if motion is MountMotionState.MOVING:
            return MountStopResult.FAILED

        return MountStopResult.UNVERIFIED

    def recover_connection(self) -> bool:
        """Attempt bounded recovery of the independent Wave path."""

        try:
            return bool(self.recovery())
        except Exception:
            return False
