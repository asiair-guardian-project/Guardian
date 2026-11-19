"""Guardian 1.0 ASIAIR monitoring commissioning."""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
)


@dataclass(frozen=True)
class AsiairMonitoringObservation:
    reachable: bool
    observed_at: datetime


def evaluate_asiair_monitoring_commissioning(
    observations: tuple[AsiairMonitoringObservation, ...],
) -> CommissioningEvidence:
    """Evaluate whether ASIAIR monitoring distinguished both reachability states."""

    saw_reachable = any(
        observation.reachable
        for observation in observations
    )
    saw_unreachable = any(
        not observation.reachable
        for observation in observations
    )

    passed = saw_reachable and saw_unreachable

    if observations:
        observed_at = max(
            observation.observed_at
            for observation in observations
        )
    else:
        raise ValueError(
            "ASIAIR monitoring commissioning requires observations"
        )

    summary = (
        "ASIAIR monitoring distinguished reachable and unreachable states"
        if passed
        else "ASIAIR monitoring did not demonstrate both reachability states"
    )

    details: Mapping[str, object] = {
        "saw_reachable": saw_reachable,
        "saw_unreachable": saw_unreachable,
        "observation_count": len(observations),
    }

    return CommissioningEvidence(
        check=CommissioningCheck.ASIAIR_MONITORING,
        completed=True,
        passed=passed,
        observed_at=observed_at,
        summary=summary,
        observations=details,
    )
