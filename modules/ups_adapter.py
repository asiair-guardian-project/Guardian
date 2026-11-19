"""Guardian 1.0 UPS reading (read-only).

Generic on purpose: unlike the v0.6 reader it does not look for one UPS model.
It uses macOS `pmset -g batt`, which lists any UPS macOS recognises over USB.

Policy (kept deliberately small):
  * on mains power            -> never "low", whatever the percentage says
  * on battery, percent known -> low when percent <= threshold
  * on battery, percent unknown -> low (an unreadable battery on battery
    power is not something to wait on)
  * UPS cannot be read at all -> NOT low for a single bad read (same as
    v0.6), but with an UpsReadTracker an UPS unreadable continuously for the
    grace period (default 15 minutes) counts as low.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass

DEFAULT_LOW_BATTERY_PERCENT = 35  # v0.6 default

_ON_BATTERY_MARKERS = (
    "Now drawing from 'UPS Power'",
    "Now drawing from 'Battery Power'",
)
_ON_MAINS_MARKER = "Now drawing from 'AC Power'"

_logger = logging.getLogger("guardian_v1.ups")


class UpsReadError(Exception):
    """The UPS state could not be determined."""


@dataclass(frozen=True)
class UpsReading:
    on_battery: bool
    battery_percent: int | None


def parse_pmset_batt(output: str) -> UpsReading:
    """Parse `pmset -g batt` output into a reading, or raise UpsReadError."""

    text = output or ""

    if any(marker in text for marker in _ON_BATTERY_MARKERS):
        on_battery = True
    elif _ON_MAINS_MARKER in text:
        on_battery = False
    else:
        raise UpsReadError("pmset output does not say which power source is in use")

    match = re.search(r"(\d{1,3})%", text)
    percent = int(match.group(1)) if match else None

    if percent is not None and percent > 100:
        raise UpsReadError(f"implausible battery percentage: {percent}")

    return UpsReading(on_battery=on_battery, battery_percent=percent)


class PmsetUpsAdapter:
    """Read the UPS through macOS `pmset`. Read-only; never changes anything."""

    def __init__(self, *, runner=subprocess.run, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def read(self) -> UpsReading:
        try:
            completed = self._runner(
                ["pmset", "-g", "batt"],
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise UpsReadError(f"unable to run pmset: {error}") from error

        if completed.returncode != 0:
            raise UpsReadError(f"pmset exited with status {completed.returncode}")

        return parse_pmset_batt(completed.stdout)


def ups_is_low(reading: UpsReading, threshold_percent: int) -> bool:
    """Apply the low-battery policy to one reading."""

    if not reading.on_battery:
        return False

    if reading.battery_percent is None:
        return True

    return reading.battery_percent <= threshold_percent


DEFAULT_UNREADABLE_GRACE_SECONDS = 900  # 15 minutes


class UpsReadTracker:
    """Remembers how long the UPS has been continuously unreadable.

    A single failed read (a USB hiccup) is ignored. If the UPS stays
    unreadable for the whole grace period, Guardian can no longer see a
    mains failure coming, so the UPS is then treated as low and the session
    aborts. Any good read resets the clock.
    """

    def __init__(
        self,
        grace_seconds: float = DEFAULT_UNREADABLE_GRACE_SECONDS,
        clock=time.monotonic,
    ) -> None:
        if grace_seconds <= 0:
            raise ValueError("grace_seconds must be positive")

        self._grace_seconds = grace_seconds
        self._clock = clock
        self._unreadable_since = None

    def low_battery(self, adapter, threshold_percent: int) -> bool:
        if adapter is None:
            return False

        try:
            reading = adapter.read()
        except Exception as error:  # a flaky reader must never crash the monitor
            now = self._clock()

            if self._unreadable_since is None:
                self._unreadable_since = now

            elapsed = now - self._unreadable_since

            if elapsed >= self._grace_seconds:
                _logger.warning(
                    "UPS unreadable for %.0f s; treating as low battery: %s",
                    elapsed,
                    error,
                )
                return True

            _logger.warning("UPS unreadable (%.0f s so far): %s", elapsed, error)
            return False

        self._unreadable_since = None
        return ups_is_low(reading, threshold_percent)


def read_ups_low_battery(
    adapter,
    threshold_percent: int = DEFAULT_LOW_BATTERY_PERCENT,
    tracker: UpsReadTracker | None = None,
) -> bool:
    """Return True only when the UPS is on battery and low.

    Without a tracker, no adapter or an unreadable UPS is reported as False
    (see module note). With a tracker, an UPS unreadable for the whole grace
    period is reported as low.
    """

    if tracker is not None:
        return tracker.low_battery(adapter, threshold_percent)

    if adapter is None:
        return False

    try:
        reading = adapter.read()
    except Exception as error:  # a flaky reader must never crash the monitor
        _logger.warning("UPS unreadable; not treated as low battery: %s", error)
        return False

    return ups_is_low(reading, threshold_percent)
