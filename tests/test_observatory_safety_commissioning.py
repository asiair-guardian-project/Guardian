from datetime import datetime, timedelta, timezone

import pytest

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    evaluate_commissioning_evidence,
)
from modules.guardian_types import RoofState
from modules.observatory_safety import ObservatorySafetyObservation
from modules.observatory_safety_commissioning import (
    evaluate_observatory_safety_commissioning,
)


NOW = datetime.now(timezone.utc)
MAX_AGE = 30.0


def observation(state, age_seconds):
    return ObservatorySafetyObservation(
        state=state,
        observed_at=NOW - timedelta(seconds=age_seconds),
    )


def test_open_closed_and_stale_unknown_verify_safety_monitoring():
    evidence = evaluate_observatory_safety_commissioning(
        (
            observation(RoofState.OPEN, 1),
            observation(RoofState.CLOSED, 2),
            observation(RoofState.OPEN, 60),
        ),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert evidence.check is CommissioningCheck.OBSERVATORY_SAFETY
    assert evidence.passed
    assert evidence.observations["saw_open"] is True
    assert evidence.observations["saw_closed"] is True
    assert evidence.observations["saw_unknown"] is True
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


def test_missing_closed_state_does_not_verify():
    evidence = evaluate_observatory_safety_commissioning(
        (
            observation(RoofState.OPEN, 1),
            observation(RoofState.OPEN, 60),
        ),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert not evidence.passed


def test_missing_open_state_does_not_verify():
    evidence = evaluate_observatory_safety_commissioning(
        (
            observation(RoofState.CLOSED, 1),
            observation(RoofState.CLOSED, 60),
        ),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert not evidence.passed


def test_missing_unknown_state_does_not_verify():
    evidence = evaluate_observatory_safety_commissioning(
        (
            observation(RoofState.OPEN, 1),
            observation(RoofState.CLOSED, 2),
        ),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert not evidence.passed


def test_empty_observations_are_rejected():
    with pytest.raises(ValueError):
        evaluate_observatory_safety_commissioning(
            (),
            now=NOW,
            max_age_seconds=MAX_AGE,
        )
