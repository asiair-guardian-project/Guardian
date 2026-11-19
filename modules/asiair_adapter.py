"""Guardian 1.0 independent ASIAIR monitoring contract."""

from typing import Protocol


class AsiairMonitorAdapter(Protocol):
    """Interface for independently observing ASIAIR reachability."""

    def is_reachable(self) -> bool:
        """Return whether the configured ASIAIR is reachable now."""
        ...
