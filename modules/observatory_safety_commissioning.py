"""Guardian 1.0 observatory-safety commissioning."""

from datetime import datetime
from typing import Mapping

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
)
from modules.guardian_types import RoofState
from modules.observatory_safety import (
    ObservatorySafetyObservation,
    normalized_roof_state,
)


def evaluate_observatory_safety_commissioning(
    observations: tuple[ObservatorySafetyObservation, ...],
    *,
    now: datetime,
    max_age_seconds: float,
) -> CommissioningEvidence:
    """Evaluate authoritative roof-state and stale-data behavior."""

    if not observations:
        raise ValueError(
            "observatory safety commissioning requires observations"
        )

    normalized = tuple(
        normalized_roof_state(
            observation,
            now=now,
            max_age_seconds=max_age_seconds,
        )
        for observation in observations
    )

    saw_open = RoofState.OPEN in normalized
    saw_closed = RoofState.CLOSED in normalized
    saw_unknown = RoofState.UNKNOWN in normalized

    passed = saw_open and saw_closed and saw_unknown

    summary = (
        "Observatory safety demonstrated OPEN, CLOSED, and UNKNOWN handling"
        if passed
        else "Observatory safety did not demonstrate all required states"
    )

    details: Mapping[str, object] = {
        "saw_open": saw_open,
        "saw_closed": saw_closed,
        "saw_unknown": saw_unknown,
        "observation_count": len(observations),
        "max_age_seconds": max_age_seconds,
    }

    return CommissioningEvidence(
        check=CommissioningCheck.OBSERVATORY_SAFETY,
        completed=True,
        passed=passed,
        observed_at=now,
        summary=summary,
        observations=details,
    )
