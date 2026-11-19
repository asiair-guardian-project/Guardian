"""Guardian 1.0 independent mount adapter contracts."""

from typing import Protocol

from modules.guardian_types import (
    Capability,
    MountMotionState,
    MountStopResult,
)


class MountAdapter(Protocol):
    """Base interface for an independent mount adapter."""

    @property
    def capabilities(self) -> frozenset[Capability]:
        """Return the independent capabilities provided by this adapter."""
        ...


class MountMotionAdapter(MountAdapter, Protocol):
    """Adapter capable of independently determining mount motion."""

    def query_motion(self) -> MountMotionState:
        """Return the current mount motion state."""
        ...


class MountStopAdapter(MountAdapter, Protocol):
    """Adapter capable of independently requesting an emergency STOP."""

    def request_stop(self) -> MountStopResult:
        """Request an immediate stop of mount motion."""
        ...


class MountStopVerificationAdapter(MountAdapter, Protocol):
    """Adapter capable of independently verifying a STOP."""

    def verify_stop(self) -> MountStopResult:
        """Verify whether the mount has stopped."""
        ...


class MountRecoveryAdapter(MountAdapter, Protocol):
    """Adapter capable of bounded independent connection recovery."""

    def recover_connection(self) -> bool:
        """Attempt bounded recovery of the independent mount connection."""
        ...
