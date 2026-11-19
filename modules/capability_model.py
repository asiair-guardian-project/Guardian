"""Guardian 1.0 capability and readiness evaluation.

Commissioning establishes which capabilities an installation requires.
Readiness determines whether those required capabilities are available now.
"""

from collections.abc import Mapping

from modules.commissioning import CommissioningStatus
from modules.guardian_types import Capability, CapabilityStatus


REQUIRED_CAPABILITIES = frozenset(
    {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
    }
)


def unavailable_required_capabilities(
    capability_statuses: Mapping[Capability, CapabilityStatus],
) -> set[Capability]:
    """Return required capabilities that are not currently AVAILABLE."""

    return {
        capability
        for capability in REQUIRED_CAPABILITIES
        if capability_statuses.get(capability) is not CapabilityStatus.AVAILABLE
    }


def protection_ready(
    capability_statuses: Mapping[Capability, CapabilityStatus],
) -> bool:
    """Return True only when every required capability is AVAILABLE."""

    return not unavailable_required_capabilities(capability_statuses)

def installation_ready(
    commissioning: CommissioningStatus | None,
    configuration_fingerprint: str,
    capability_statuses: Mapping[Capability, CapabilityStatus],
) -> bool:
    """Return whether the commissioned installation is ready now."""

    return (
        commissioning is not None
        and commissioning.valid_for_configuration(configuration_fingerprint)
        and protection_ready(capability_statuses)
    )

