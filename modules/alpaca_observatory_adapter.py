"""Guardian 1.0 Alpaca observatory safety adapter."""

from datetime import datetime, timezone

from modules.alpaca_safety_monitor import read_alpaca_safety_status
from modules.guardian_types import RoofState
from modules.observatory_safety import ObservatorySafetyObservation


class AlpacaObservatorySafetyAdapter:
    """Read an Alpaca SafetyMonitor as an observatory safety source."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        device_number: int,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not host:
            raise ValueError("Alpaca host is required")

        if port <= 0:
            raise ValueError("Alpaca port must be positive")

        if device_number < 0:
            raise ValueError("device_number must be non-negative")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._host = host
        self._port = port
        self._device_number = device_number
        self._timeout_seconds = timeout_seconds

    def observe(self) -> ObservatorySafetyObservation:
        result = read_alpaca_safety_status(
            self._host,
            self._port,
            self._device_number,
            timeout_seconds=self._timeout_seconds,
        )

        state = (
            RoofState.OPEN
            if result["is_safe"]
            else RoofState.CLOSED
        )

        return ObservatorySafetyObservation(
            state=state,
            observed_at=datetime.now(timezone.utc),
        )
