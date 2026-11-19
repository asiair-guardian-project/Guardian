"""Guardian 1.0 runtime capability status registry."""

from collections.abc import Mapping

from modules.guardian_types import Capability, CapabilityStatus


class CapabilityRegistry:
    """Own the current runtime status of Guardian capabilities."""

    def __init__(
        self,
        configured_capabilities: set[Capability],
    ) -> None:
        self._configured = frozenset(configured_capabilities)

        self._statuses = {
            capability: (
                CapabilityStatus.UNKNOWN
                if capability in self._configured
                else CapabilityStatus.UNAVAILABLE
            )
            for capability in Capability
        }

    @property
    def configured_capabilities(self) -> frozenset[Capability]:
        return self._configured

    def status(self, capability: Capability) -> CapabilityStatus:
        return self._statuses[capability]

    def update(
        self,
        capability: Capability,
        status: CapabilityStatus,
    ) -> None:
        """Update one configured capability."""

        if capability not in self._configured:
            raise ValueError(
                f"capability is not configured: {capability.name}"
            )

        self._statuses[capability] = status

    def update_many(
        self,
        statuses: Mapping[Capability, CapabilityStatus],
    ) -> None:
        """Update multiple configured capabilities."""

        unconfigured = set(statuses) - self._configured

        if unconfigured:
            names = ", ".join(
                sorted(capability.name for capability in unconfigured)
            )
            raise ValueError(
                f"capabilities are not configured: {names}"
            )

        self._statuses.update(statuses)

    def snapshot(self) -> dict[Capability, CapabilityStatus]:
        """Return an independent snapshot of all capability statuses."""

        return dict(self._statuses)

    def available_capabilities(self) -> frozenset[Capability]:
        """Return capabilities currently known to be AVAILABLE."""

        return frozenset(
            capability
            for capability, status in self._statuses.items()
            if status is CapabilityStatus.AVAILABLE
        )
