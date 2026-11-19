"""Guardian 1.0 capability probe coordination."""

from collections.abc import Iterable

from modules.capability_probe import CapabilityProbeResult
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import Capability


def apply_probe_results(
    *,
    registry: CapabilityRegistry,
    results: Iterable[CapabilityProbeResult],
) -> None:
    """Validate and atomically apply capability probe results."""

    results = tuple(results)

    seen: set[Capability] = set()

    for result in results:
        if result.capability in seen:
            raise ValueError(
                f"duplicate probe result for {result.capability.name}"
            )

        seen.add(result.capability)

        if result.capability not in registry.configured_capabilities:
            raise ValueError(
                f"capability is not configured: "
                f"{result.capability.name}"
            )

    registry.update_many(
        {
            result.capability: result.status
            for result in results
        }
    )
