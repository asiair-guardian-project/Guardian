"""Guardian 1.0 generic Safety Power Controller contracts."""

from typing import Protocol

from modules.guardian_types import (
    SafetyPowerResult,
    SafetyPowerState,
)
from modules.safety_power import SafetyPowerEndpoint


class SafetyPowerAdapter(Protocol):
    """Minimum interface for any Safety Power Controller."""

    @property
    def controller_id(self) -> str:
        ...

    @property
    def supports_verification(self) -> bool:
        ...

    def check_endpoint(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> bool:
        """
        Non-destructively confirm that an endpoint is accessible
        and matches the controller's configured identity.
        """
        ...

    def power_off(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerResult:
        """Command an endpoint OFF."""
        ...


class SafetyPowerStateAdapter(SafetyPowerAdapter, Protocol):
    """Controller capable of reporting endpoint power state."""

    def get_power_state(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerState:
        ...


class SafetyPowerVerificationAdapter(
    SafetyPowerStateAdapter,
    Protocol,
):
    """Controller capable of explicit OFF verification."""

    def verify_off(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerResult:
        ...
