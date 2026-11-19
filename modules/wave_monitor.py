from modules.wave_interface import (
    WaveCommunicationError,
    WaveInterface,
)


class WaveMonitorError(Exception):
    """Raised when Wave status cannot be read."""


def read_wave_status(host="192.168.4.1", port=11880, timeout=3):
    """
    Read current Wave 150i status.

    This function is read-only.
    It does not issue STOP, slew, home, tracking, or initialization commands.
    """

    wave = WaveInterface(
        host=host,
        port=port,
        timeout=timeout,
    )

    try:
        axis1_status = wave.get_status(1)
        axis1_position = wave.get_position(1)

        axis2_status = wave.get_status(2)
        axis2_position = wave.get_position(2)

    except WaveCommunicationError as error:
        raise WaveMonitorError(
            f"Unable to read Wave status: {error}"
        ) from error

    return {
        "reachable": True,
        "axis1": {
            "status": axis1_status,
            "position": axis1_position,
        },
        "axis2": {
            "status": axis2_status,
            "position": axis2_position,
        },
    }