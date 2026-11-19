"""Spacing and debouncing of the Safety Power (strip) health check.

The HS300 strip does not like closely spaced connections. Guardian therefore
checks it on a schedule (default once a minute, over one connection) instead
of every 5-second cycle, and one failed check does not by itself mark the
strip unavailable: it takes `failures_to_degrade` (3, the same three attempts
v0.6 makes) in a row, retried on the following cycles about 4-5 s apart. The
emergency cut path never uses this schedule.
"""

from __future__ import annotations

import time

from modules.guardian_types import CapabilityStatus

DEFAULT_CHECK_INTERVAL_SECONDS = 60.0
DEFAULT_RETRY_AFTER_FAILURE_SECONDS = 4.0   # lands on the next 5 s cycle
DEFAULT_FAILURES_TO_DEGRADE = 3             # three attempts, as v0.6 does


class SafetyPowerProbeSchedule:
    def __init__(
        self,
        *,
        interval_seconds=DEFAULT_CHECK_INTERVAL_SECONDS,
        retry_after_failure_seconds=DEFAULT_RETRY_AFTER_FAILURE_SECONDS,
        failures_to_degrade=DEFAULT_FAILURES_TO_DEGRADE,
        clock=time.monotonic,
    ):
        if interval_seconds <= 0 or retry_after_failure_seconds <= 0:
            raise ValueError("intervals must be positive")
        if failures_to_degrade < 1:
            raise ValueError("failures_to_degrade must be at least 1")

        self._interval = interval_seconds
        self._retry = retry_after_failure_seconds
        self._failures_to_degrade = failures_to_degrade
        self._clock = clock
        self._next_due = None
        self._failures = 0

    def run(self, probe):
        """Run probe() if due. Return a result to apply, or None to keep the last one."""

        now = self._clock()

        if self._next_due is not None and now < self._next_due:
            return None

        result = probe()

        if result.status is CapabilityStatus.AVAILABLE:
            self._failures = 0
            self._next_due = now + self._interval
            return result

        self._failures += 1
        self._next_due = now + self._retry

        if self._failures >= self._failures_to_degrade:
            return result

        return None  # first failure: keep the last status, look again soon
