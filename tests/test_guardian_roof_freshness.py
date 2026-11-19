"""Isolated roof-status freshness regression tests."""

from datetime import datetime, timedelta

import pytest

from modules.roof_monitor import read_roof_status
from modules.roof_freshness import (
    roof_status_age_seconds,
    roof_status_is_stale,
)


NOW = datetime(2026, 10, 16, 16, 0, 0)


@pytest.mark.parametrize(
    "age_seconds, expected_stale",
    [
        (30, False),
        (60, False),
        (61, True),
        (600, True),
    ],
)
def test_roof_status_freshness_from_temporary_file(
    tmp_path, age_seconds, expected_stale
):
    roof_file = tmp_path / "roof_status.txt"
    timestamp = NOW - timedelta(seconds=age_seconds)

    roof_file.write_text(
        timestamp.strftime(
            "%Y-%m-%d %I:%M:%S%p CST Roof Status: CLOSED\n"
        ),
        encoding="utf-8",
    )

    parsed = read_roof_status(roof_file)

    assert parsed["status"] == "CLOSED"
    assert parsed["timestamp"] == timestamp
    assert roof_status_age_seconds(timestamp, now=NOW) == age_seconds
    assert roof_status_is_stale(
        parsed["timestamp"],
        stale_after_seconds=60,
        now=NOW,
    ) is expected_stale


@pytest.mark.parametrize(
    "seconds_ahead, expected_stale",
    [
        (5, False),
        (6, True),
    ],
)
def test_roof_status_future_timestamp_tolerance(
    tmp_path, seconds_ahead, expected_stale
):
    roof_file = tmp_path / "roof_status.txt"
    timestamp = NOW + timedelta(seconds=seconds_ahead)

    roof_file.write_text(
        timestamp.strftime(
            "%Y-%m-%d %I:%M:%S%p CST Roof Status: OPEN\n"
        ),
        encoding="utf-8",
    )

    parsed = read_roof_status(roof_file)

    assert parsed["status"] == "OPEN"
    assert roof_status_is_stale(
        parsed["timestamp"],
        stale_after_seconds=60,
        now=NOW,
    ) is expected_stale
