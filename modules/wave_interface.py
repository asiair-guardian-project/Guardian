import socket


class WaveCommunicationError(Exception):
    """Raised when communication with the Wave mount fails."""


class WaveInterface:
    """Minimal read/stop interface for the Sky-Watcher Wave mount."""

    def __init__(self, host="192.168.4.1", port=11880, timeout=3):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send_command(self, command):
        """
        Send one Sky-Watcher motor-controller command.

        Returns the raw response string without the trailing carriage return.
        """

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        sock.settimeout(self.timeout)

        try:
            sock.sendto(
                command.encode("ascii"),
                (self.host, self.port),
            )

            response, _ = sock.recvfrom(1024)

        except (OSError, socket.timeout) as error:
            raise WaveCommunicationError(
                f"Wave communication failed: {error}"
            ) from error

        finally:
            sock.close()

        try:
            response_text = response.decode("ascii").rstrip("\r")

        except UnicodeDecodeError as error:
            raise WaveCommunicationError(
                "Wave returned a non-ASCII response."
            ) from error

        if not response_text:
            raise WaveCommunicationError(
                "Wave returned an empty response."
            )

        if response_text.startswith("!"):
            raise WaveCommunicationError(
                f"Wave returned an error: {response_text}"
            )

        if not response_text.startswith("="):
            raise WaveCommunicationError(
                f"Unexpected Wave response: {response_text}"
            )

        return response_text

    def get_version(self, axis):
        """Read the motor-controller version for one axis."""

        return self._send_command(
            f":e{axis}\r"
        )

    def get_status(self, axis):
        """Read the raw motor status for one axis."""

        return self._send_command(
            f":f{axis}\r"
        )

    def get_position(self, axis):
        """Read the raw motor position for one axis."""

        return self._send_command(
            f":j{axis}\r"
        )

    def stop(self, axis):
        """Issue the documented controlled STOP command."""

        return self._send_command(
            f":K{axis}\r"
        )