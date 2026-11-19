"""Guardian 1.0 observatory safety adapter contract."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from modules.guardian_types import RoofState


@dataclass(frozen=True)
class ObservatorySafetyObservation:
    """Normalized observation from an observatory safety source."""

    state: RoofState
    observed_at: datetime


class ObservatorySafetyAdapter(Protocol):
    """Interface implemented by observatory-specific safety adapters."""

    def observe(self) -> ObservatorySafetyObservation:
        """Return the latest normalized observatory safety observation."""
        ...


def normalized_roof_state(
    observation: ObservatorySafetyObservation,
    *,
    now: datetime,
    max_age_seconds: float,
) -> RoofState:
    """Return UNKNOWN when an observatory safety observation is stale."""

    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")

    age_seconds = (now - observation.observed_at).total_seconds()

    if age_seconds < 0:
        return RoofState.UNKNOWN

    if age_seconds > max_age_seconds:
        return RoofState.UNKNOWN

    return observation.state
