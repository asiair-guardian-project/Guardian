from datetime import datetime, timedelta, timezone

from modules.guardian_types import RoofState
from modules.guardian_v1_roof_filter import GuardianV1RoofFilter


START = datetime(2026, 10, 12, tzinfo=timezone.utc)


def at(seconds):
    return START + timedelta(seconds=seconds)


def test_open_is_accepted_immediately():
    result = GuardianV1RoofFilter().evaluate(RoofState.OPEN, now=at(0))
    assert result.effective_state is RoofState.OPEN
    assert not result.timed_out


def test_closed_is_accepted_immediately():
    result = GuardianV1RoofFilter().evaluate(RoofState.CLOSED, now=at(0))
    assert result.effective_state is RoofState.CLOSED
    assert not result.timed_out


def test_unknown_recovers_and_resets_counter():
    roof = GuardianV1RoofFilter()

    for i in range(6):
        roof.evaluate(RoofState.UNKNOWN, now=at(i * 5))

    recovered = roof.evaluate(RoofState.OPEN, now=at(30))
    assert recovered.effective_state is RoofState.OPEN
    assert recovered.consecutive_unknown == 0

    again = roof.evaluate(RoofState.UNKNOWN, now=at(35))
    assert again.consecutive_unknown == 1
    assert not again.timed_out


def test_twelve_unknown_readings_before_sixty_seconds_do_not_timeout():
    roof = GuardianV1RoofFilter()

    for i in range(12):
        result = roof.evaluate(RoofState.UNKNOWN, now=at(i * 5))

    assert result.consecutive_unknown == 12
    assert result.unknown_seconds == 55
    assert result.effective_state is RoofState.UNKNOWN
    assert not result.timed_out


def test_unknown_times_out_after_twelve_readings_and_sixty_seconds():
    roof = GuardianV1RoofFilter()

    for i in range(13):
        result = roof.evaluate(RoofState.UNKNOWN, now=at(i * 5))

    assert result.consecutive_unknown == 13
    assert result.unknown_seconds == 60
    assert result.effective_state is RoofState.CLOSED
    assert result.timed_out


def test_elapsed_time_alone_is_insufficient():
    roof = GuardianV1RoofFilter()

    roof.evaluate(RoofState.UNKNOWN, now=at(0))
    result = roof.evaluate(RoofState.UNKNOWN, now=at(65))

    assert result.consecutive_unknown == 2
    assert not result.timed_out


def test_confirmed_closed_resets_unknown_streak():
    roof = GuardianV1RoofFilter()

    for i in range(6):
        roof.evaluate(RoofState.UNKNOWN, now=at(i * 5))

    result = roof.evaluate(RoofState.CLOSED, now=at(30))
    assert result.effective_state is RoofState.CLOSED
    assert result.consecutive_unknown == 0
    assert not result.timed_out
