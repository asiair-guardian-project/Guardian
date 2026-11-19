from datetime import datetime, timedelta, timezone

from modules.guardian_types import RoofState
from modules.observatory_safety import (
    ObservatorySafetyObservation,
    normalized_roof_state,
)


NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


def test_fresh_open_remains_open():
    observation = ObservatorySafetyObservation(
        state=RoofState.OPEN,
        observed_at=NOW - timedelta(seconds=5),
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.OPEN


def test_fresh_closed_remains_closed():
    observation = ObservatorySafetyObservation(
        state=RoofState.CLOSED,
        observed_at=NOW - timedelta(seconds=5),
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.CLOSED


def test_explicit_unknown_remains_unknown():
    observation = ObservatorySafetyObservation(
        state=RoofState.UNKNOWN,
        observed_at=NOW,
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.UNKNOWN


def test_stale_open_becomes_unknown():
    observation = ObservatorySafetyObservation(
        state=RoofState.OPEN,
        observed_at=NOW - timedelta(seconds=11),
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.UNKNOWN


def test_stale_closed_becomes_unknown():
    observation = ObservatorySafetyObservation(
        state=RoofState.CLOSED,
        observed_at=NOW - timedelta(seconds=11),
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.UNKNOWN


def test_future_timestamp_becomes_unknown():
    observation = ObservatorySafetyObservation(
        state=RoofState.OPEN,
        observed_at=NOW + timedelta(seconds=1),
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.UNKNOWN


def test_exact_age_limit_is_still_fresh():
    observation = ObservatorySafetyObservation(
        state=RoofState.OPEN,
        observed_at=NOW - timedelta(seconds=10),
    )

    assert normalized_roof_state(
        observation,
        now=NOW,
        max_age_seconds=10,
    ) is RoofState.OPEN


def test_negative_max_age_is_rejected():
    observation = ObservatorySafetyObservation(
        state=RoofState.OPEN,
        observed_at=NOW,
    )

    try:
        normalized_roof_state(
            observation,
            now=NOW,
            max_age_seconds=-1,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("negative max_age_seconds should be rejected")
