"""Guardian 1.0 protection incident coordination.

The coordinator joins protection triggers, response planning, execution,
incident recording, and the latched ABORTED session state. Hardware access
remains injected through an executor.
"""

import time
from dataclasses import dataclass, field

from modules.guardian_types import (
    Capability,
    ProtectionAction,
    ProtectionTrigger,
    SessionState,
)
from modules.protection_execution import (
    ProtectionActionRecord,
    execute_protection_plan,
    unresolved_safety_power_actions,
)
from modules.protection_planner import build_protection_plan


# Retry pacing for an unresolved shutdown, measured from the incident's first
# attempt and matching v0.6: every 15 s for 2 minutes, then every minute up to
# 12 minutes, then every 5 minutes. The strip does not like being hammered.
RETRY_SCHEDULE_SECONDS = ((120.0, 15.0), (720.0, 60.0))
RETRY_LATE_INTERVAL_SECONDS = 300.0

_now = time.monotonic  # replaced in tests


def retry_interval_seconds(elapsed_seconds: float) -> float:
    for limit, interval in RETRY_SCHEDULE_SECONDS:
        if elapsed_seconds < limit:
            return interval

    return RETRY_LATE_INTERVAL_SECONDS


@dataclass
class ProtectionIncident:
    """Complete Core record of one Guardian protection incident."""

    triggers: set[ProtectionTrigger]
    plan: list[ProtectionAction]
    lost_capabilities: set[Capability] = field(default_factory=set)
    records: list[ProtectionActionRecord] = field(default_factory=list)
    session_state: SessionState = SessionState.ABORTED
    # Pacing state is runtime-only: never saved, so a restored incident
    # retries immediately.
    _first_attempt_at: float | None = field(
        default=None, init=False, repr=False, compare=False)
    _last_attempt_at: float | None = field(
        default=None, init=False, repr=False, compare=False)

    def note_attempt_made(self) -> None:
        now = _now()

        if self._first_attempt_at is None:
            self._first_attempt_at = now

        self._last_attempt_at = now

    def retry_due(self) -> bool:
        if self._last_attempt_at is None:
            return True

        now = _now()
        started = self._first_attempt_at if self._first_attempt_at is not None else now
        return now - self._last_attempt_at >= retry_interval_seconds(now - started)

    @property
    def safety_power_control_lost(self) -> bool:
        """Return whether Safety Power control caused this incident."""

        return (
            Capability.SAFETY_POWER_CONTROL
            in self.lost_capabilities
        )

    @property
    def unresolved_actions(self) -> list[ProtectionAction]:
        # Every required power role must have a verified shutdown result.
        return unresolved_safety_power_actions(self.records)

    def retry_unresolved(
        self,
        execute_action,
        execute_safety_power=None,
    ) -> list[ProtectionActionRecord]:
        """Retry unresolved required Safety Power actions and retain history."""

        retry_plan = self.unresolved_actions

        if not retry_plan:
            return []

        if not self.retry_due():
            return []

        retry_records = execute_protection_plan(
            plan=retry_plan,
            execute_action=execute_action,
            execute_safety_power=execute_safety_power,
        )
        self.note_attempt_made()

        self.records.extend(retry_records)
        return retry_records



def initiate_protection(
    *,
    triggers: set[ProtectionTrigger],
    lost_capabilities: set[Capability] | None = None,
    execute_action,
    execute_safety_power=None,
) -> ProtectionIncident:
    """Create and execute a protection incident.

    At least one evaluated protection trigger is required. Once the initial
    protection sequence has been attempted, the incident is latched ABORTED
    regardless of whether every required action succeeded.
    """

    if not triggers:
        raise ValueError("cannot initiate protection without a trigger")

    plan = build_protection_plan()

    records = execute_protection_plan(
        plan=plan,
        execute_action=execute_action,
        execute_safety_power=execute_safety_power,
    )

    incident = ProtectionIncident(
        triggers=set(triggers),
        plan=plan,
        lost_capabilities=set(lost_capabilities or set()),
        records=records,
        session_state=SessionState.ABORTED,
    )
    incident.note_attempt_made()
    return incident
