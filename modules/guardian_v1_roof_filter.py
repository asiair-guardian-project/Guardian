"""Guardian 1.0 roof UNKNOWN recovery filter.

Pure decision logic. No hardware operations.
"""

from dataclasses import dataclass
from datetime import datetime
from modules.guardian_types import RoofState


@dataclass(frozen=True)
class RoofFilterResult:
    effective_state: RoofState
    consecutive_unknown: int
    unknown_seconds: float
    timed_out: bool


class GuardianV1RoofFilter:
    def __init__(self, *, threshold=12, grace_seconds=60):
        if threshold < 1 or grace_seconds <= 0:
            raise ValueError("Invalid UNKNOWN recovery settings")

        self.threshold = threshold
        self.grace_seconds = grace_seconds
        self._unknown_since = None
        self._unknown_count = 0

    def evaluate(self, state: RoofState, *, now: datetime) -> RoofFilterResult:
        if state is not RoofState.UNKNOWN:
            self._unknown_since = None
            self._unknown_count = 0
            return RoofFilterResult(state, 0, 0.0, False)

        if self._unknown_since is None:
            self._unknown_since = now

        self._unknown_count += 1
        elapsed = max(0.0, (now - self._unknown_since).total_seconds())
        timed_out = (
            self._unknown_count >= self.threshold
            and elapsed >= self.grace_seconds
        )

        return RoofFilterResult(
            effective_state=RoofState.CLOSED if timed_out else RoofState.UNKNOWN,
            consecutive_unknown=self._unknown_count,
            unknown_seconds=elapsed,
            timed_out=timed_out,
        )
