"""Guardian 1.0 ASIAIR session-state tracking.

Raw ASIAIR reachability is converted into session-aware state so an ASIAIR
that has not yet appeared is distinguished from one that was established and
then lost.
"""

from modules.guardian_types import AsiairState


# Guardian 1.0 requires this many unanswered checks IN A ROW before an
# established ASIAIR counts as lost, so one dropped ping cannot cut power.
DEFAULT_LOST_AFTER_MISSES = 2


class AsiairStateTracker:
    """Track ASIAIR state for the current Guardian session.

    lost_after_misses=1 (the class default) reports LOST on the first
    unreachable observation; Guardian's compositions pass
    DEFAULT_LOST_AFTER_MISSES. Any reachable observation resets the count.
    """

    def __init__(self, lost_after_misses: int = 1) -> None:
        if lost_after_misses < 1:
            raise ValueError("lost_after_misses must be at least 1")

        self._lost_after_misses = lost_after_misses
        self._misses = 0
        self._state = AsiairState.NOT_ESTABLISHED
        self._was_established = False

    @property
    def state(self) -> AsiairState:
        return self._state

    def observe(self, reachable: bool) -> AsiairState:
        """Update state from the latest raw reachability observation."""

        if reachable:
            self._misses = 0
            self._was_established = True
            self._state = AsiairState.ONLINE
        elif self._was_established:
            self._misses += 1

            if self._misses >= self._lost_after_misses:
                self._state = AsiairState.LOST
        else:
            self._state = AsiairState.NOT_ESTABLISHED

        return self._state

    def reset(self) -> AsiairState:
        """Reset ASIAIR establishment history for a new session."""

        self._was_established = False
        self._misses = 0
        self._state = AsiairState.NOT_ESTABLISHED
        return self._state
