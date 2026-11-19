"""Guardian 1.0 capability probe results."""

from dataclasses import dataclass
from typing import Generic, TypeVar

from modules.guardian_types import Capability, CapabilityStatus


ObservationT = TypeVar("ObservationT")


@dataclass(frozen=True)
class CapabilityProbeResult(Generic[ObservationT]):
    """Result of probing one configured Guardian capability.

    Capability status describes whether the independent Guardian path works.
    Observation describes what that working path observed about the device or
    service. These are intentionally separate concepts.
    """

    capability: Capability
    status: CapabilityStatus
    observation: ObservationT | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status is CapabilityStatus.UNAVAILABLE:
            raise ValueError(
                "configured capability probes must not report UNAVAILABLE"
            )
