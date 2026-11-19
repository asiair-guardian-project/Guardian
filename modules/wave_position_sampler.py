import time

from modules.wave_interface import (
    WaveCommunicationError,
    WaveInterface,
)


class WavePositionSamplerError(Exception):
    """Raised when Wave position sampling fails."""


def decode_position(raw_position):
    """
    Decode a Sky-Watcher 24-bit motor position response.

    Example raw response:
        =803471

    The three position bytes are transmitted least-significant byte first.
    """

    value = raw_position.lstrip("=")

    if len(value) != 6:
        raise WavePositionSamplerError(
            f"Unexpected Wave position format: {raw_position}"
        )

    try:
        byte0 = int(value[0:2], 16)
        byte1 = int(value[2:4], 16)
        byte2 = int(value[4:6], 16)

    except ValueError as error:
        raise WavePositionSamplerError(
            f"Invalid Wave position value: {raw_position}"
        ) from error

    return byte0 | (byte1 << 8) | (byte2 << 16)


def sample_positions(interval_seconds=2):
    """
    Take two read-only position samples from both Wave axes.

    Returns decoded positions and raw count changes.
    No safety decision or motor command is performed.
    """

    wave = WaveInterface()

    try:
        axis1_before_raw = wave.get_position(1)
        axis2_before_raw = wave.get_position(2)

        time.sleep(interval_seconds)

        axis1_after_raw = wave.get_position(1)
        axis2_after_raw = wave.get_position(2)

    except WaveCommunicationError as error:
        raise WavePositionSamplerError(
            f"Unable to sample Wave positions: {error}"
        ) from error

    axis1_before = decode_position(axis1_before_raw)
    axis1_after = decode_position(axis1_after_raw)

    axis2_before = decode_position(axis2_before_raw)
    axis2_after = decode_position(axis2_after_raw)

    return {
        "interval_seconds": interval_seconds,
        "axis1": {
            "before_raw": axis1_before_raw,
            "after_raw": axis1_after_raw,
            "before": axis1_before,
            "after": axis1_after,
            "delta": axis1_after - axis1_before,
        },
        "axis2": {
            "before_raw": axis2_before_raw,
            "after_raw": axis2_after_raw,
            "before": axis2_before,
            "after": axis2_after,
            "delta": axis2_after - axis2_before,
        },
    }

def wave_is_moving(sample_result):
    """
    Return True if either Wave axis changed position
    between the two samples.

    This function makes no motor commands.
    """

    axis1_delta = sample_result["axis1"]["delta"]
    axis2_delta = sample_result["axis2"]["delta"]

    return axis1_delta != 0 or axis2_delta != 0