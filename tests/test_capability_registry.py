import pytest

from modules.guardian_types import Capability, CapabilityStatus
from modules.capability_registry import CapabilityRegistry


def test_configured_capability_starts_unknown():
    registry = CapabilityRegistry(
        {Capability.ASIAIR_MONITORING}
    )

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


def test_unconfigured_capability_is_unavailable():
    registry = CapabilityRegistry(
        {Capability.ASIAIR_MONITORING}
    )

    assert (
        registry.status(Capability.INDEPENDENT_MOUNT_STOP)
        is CapabilityStatus.UNAVAILABLE
    )


def test_configured_capability_can_be_updated():
    registry = CapabilityRegistry(
        {Capability.ASIAIR_MONITORING}
    )

    registry.update(
        Capability.ASIAIR_MONITORING,
        CapabilityStatus.AVAILABLE,
    )

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )


def test_unconfigured_capability_cannot_be_updated():
    registry = CapabilityRegistry(
        {Capability.ASIAIR_MONITORING}
    )

    with pytest.raises(ValueError):
        registry.update(
            Capability.INDEPENDENT_MOUNT_STOP,
            CapabilityStatus.AVAILABLE,
        )


def test_update_many_is_atomic_for_configuration_validation():
    registry = CapabilityRegistry(
        {
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
        }
    )

    with pytest.raises(ValueError):
        registry.update_many(
            {
                Capability.ASIAIR_MONITORING:
                    CapabilityStatus.AVAILABLE,
                Capability.INDEPENDENT_MOUNT_STOP:
                    CapabilityStatus.AVAILABLE,
            }
        )

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


def test_snapshot_is_independent_copy():
    registry = CapabilityRegistry(
        {Capability.ASIAIR_MONITORING}
    )

    snapshot = registry.snapshot()
    snapshot[Capability.ASIAIR_MONITORING] = (
        CapabilityStatus.AVAILABLE
    )

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


def test_available_capabilities_reports_only_available():
    registry = CapabilityRegistry(
        {
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
        }
    )

    registry.update(
        Capability.ASIAIR_MONITORING,
        CapabilityStatus.AVAILABLE,
    )

    assert registry.available_capabilities() == frozenset(
        {Capability.ASIAIR_MONITORING}
    )
