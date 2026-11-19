import pytest

from modules.capability_probe import CapabilityProbeResult
from modules.capability_probe_coordinator import apply_probe_results
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import Capability, CapabilityStatus


def registry():
    return CapabilityRegistry(
        {
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
        }
    )


def test_probe_results_update_registry():
    capabilities = registry()

    apply_probe_results(
        registry=capabilities,
        results=[
            CapabilityProbeResult(
                capability=Capability.ASIAIR_MONITORING,
                status=CapabilityStatus.AVAILABLE,
                observation=False,
            ),
            CapabilityProbeResult(
                capability=Capability.OBSERVATORY_SAFETY_MONITORING,
                status=CapabilityStatus.AVAILABLE,
            ),
        ],
    )

    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        capabilities.status(
            Capability.OBSERVATORY_SAFETY_MONITORING
        )
        is CapabilityStatus.AVAILABLE
    )


def test_negative_device_observation_does_not_change_capability_status():
    capabilities = registry()

    apply_probe_results(
        registry=capabilities,
        results=[
            CapabilityProbeResult(
                capability=Capability.ASIAIR_MONITORING,
                status=CapabilityStatus.AVAILABLE,
                observation=False,
            ),
        ],
    )

    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )


def test_duplicate_probe_result_is_rejected_without_updates():
    capabilities = registry()

    with pytest.raises(ValueError):
        apply_probe_results(
            registry=capabilities,
            results=[
                CapabilityProbeResult(
                    capability=Capability.ASIAIR_MONITORING,
                    status=CapabilityStatus.AVAILABLE,
                ),
                CapabilityProbeResult(
                    capability=Capability.ASIAIR_MONITORING,
                    status=CapabilityStatus.FAILED,
                ),
            ],
        )

    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


def test_unconfigured_probe_result_is_rejected_without_updates():
    capabilities = registry()

    with pytest.raises(ValueError):
        apply_probe_results(
            registry=capabilities,
            results=[
                CapabilityProbeResult(
                    capability=Capability.ASIAIR_MONITORING,
                    status=CapabilityStatus.AVAILABLE,
                ),
                CapabilityProbeResult(
                    capability=Capability.INDEPENDENT_MOUNT_STOP,
                    status=CapabilityStatus.AVAILABLE,
                ),
            ],
        )

    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


def test_empty_probe_batch_does_nothing():
    capabilities = registry()

    apply_probe_results(
        registry=capabilities,
        results=[],
    )

    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )
