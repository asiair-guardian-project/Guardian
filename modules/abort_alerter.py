"""Optional phone alert for Guardian 1.0 aborts. OFF by default.

Operator choice, one setting:
  OFF      never send anything (default; what the Starfront operator wants)
  FAILURE  send only when power-off is NOT verified, i.e. the rig may still
           be powered and someone awake could cut it with the Kasa app
  ALL      send on every abort, and again if a power-off then fails

This module only decides WHETHER to send and what the text says. The sender
is supplied by the caller (for example the existing Pushover sender), so
nothing here talks to the network. A failing sender can never affect
protection: its errors are swallowed.
"""

from __future__ import annotations

import logging
from enum import Enum

_logger = logging.getLogger("guardian_v1.alert")


class AlertLevel(Enum):
    OFF = "off"
    FAILURE = "failure"
    ALL = "all"

    @classmethod
    def parse(cls, value) -> "AlertLevel":
        if value is None:
            return cls.OFF

        if isinstance(value, cls):
            return value

        try:
            return cls(str(value).strip().lower())
        except ValueError:
            raise ValueError(
                f"alert level must be one of off, failure, all; got {value!r}"
            ) from None


class AbortAlerter:
    """Call observe() with the current incident after every runtime cycle."""

    def __init__(
        self,
        level=AlertLevel.OFF,
        send=None,
        failure_confirm_cycles: int = 3,
    ) -> None:
        # A power-off that fails once and succeeds on the next retry (a Wi-Fi
        # blip) is not worth waking anyone for: the failure alert waits until
        # the power-off has stayed unresolved this many cycles in a row.
        if failure_confirm_cycles < 1:
            raise ValueError("failure_confirm_cycles must be at least 1")

        self._level = AlertLevel.parse(level)
        self._send = send
        self._failure_confirm_cycles = failure_confirm_cycles
        self._incident = None
        self._sent_abort = False
        self._sent_failure = False
        self._unresolved_cycles = 0

    @property
    def level(self) -> AlertLevel:
        return self._level

    def observe(self, incident) -> int:
        """Send any alert now due. Returns how many were sent (0, 1 or 2)."""

        if incident is None:
            self._incident = None
            self._sent_abort = False
            self._sent_failure = False
            self._unresolved_cycles = 0
            return 0

        if incident is not self._incident:
            self._incident = incident
            self._sent_abort = False
            self._sent_failure = False
            self._unresolved_cycles = 0

        if self._level is AlertLevel.OFF or self._send is None:
            return 0

        sent = 0
        causes = ", ".join(sorted(t.name for t in incident.triggers))

        if self._level is AlertLevel.ALL and not self._sent_abort:
            self._sent_abort = True
            sent += self._deliver("WARNING", f"Guardian ABORT: {causes}")

        unresolved = incident.unresolved_actions
        self._unresolved_cycles = self._unresolved_cycles + 1 if unresolved else 0

        if (
            unresolved
            and not self._sent_failure
            and self._unresolved_cycles >= self._failure_confirm_cycles
        ):
            self._sent_failure = True
            names = ", ".join(sorted(a.name for a in unresolved))
            sent += self._deliver(
                "CRITICAL",
                f"Guardian ABORT FAILED ({causes}): power-off not verified "
                f"for {names}. The rig may still be powered.",
            )

        return sent

    def _deliver(self, level: str, message: str) -> int:
        try:
            self._send(level, message)
        except Exception as error:  # an alert problem must never stop protection
            _logger.warning("abort alert could not be sent: %s", error)
            return 0

        return 1
