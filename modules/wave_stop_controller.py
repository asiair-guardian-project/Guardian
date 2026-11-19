import time

from modules.wave_interface import (
    WaveCommunicationError,
    WaveInterface,
)


class WaveStopError(Exception):
    """Raised when the Wave cannot be safely stopped and verified."""


def stop_wave_safely(
    wave=None,
    verification_interval_seconds=2,
):
    """
    Stop both Wave axes and verify that both remain stationary.

    Returns verification details on success.
    Raises WaveStopError if communication or verification fails.
    """

    if wave is None:
        wave = WaveInterface()

    try:
        axis1_stop_response = wave.stop(1)
        axis2_stop_response = wave.stop(2)

        axis1_before = wave.get_position(1)
        axis2_before = wave.get_position(2)

        time.sleep(verification_interval_seconds)

        axis1_after = wave.get_position(1)
        axis2_after = wave.get_position(2)

    except WaveCommunicationError as error:
        raise WaveStopError(
            f"Wave stop communication failed: {error}"
        ) from error

    axis1_stopped = axis1_before == axis1_after
    axis2_stopped = axis2_before == axis2_after

    if not axis1_stopped or not axis2_stopped:
        raise WaveStopError(
            "Wave stop verification failed: "
            f"Axis 1 stopped={axis1_stopped}, "
            f"Axis 2 stopped={axis2_stopped}."
        )

    return {
        "success": True,
        "axis1": {
            "stop_response": axis1_stop_response,
            "before": axis1_before,
            "after": axis1_after,
            "stopped": axis1_stopped,
        },
        "axis2": {
            "stop_response": axis2_stop_response,
            "before": axis2_before,
            "after": axis2_after,
            "stopped": axis2_stopped,
        },
    }