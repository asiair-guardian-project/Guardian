import pytest

from modules.asiair_observation_coordinator import process_asiair_probe
from modules.asiair_state import AsiairStateTracker
from modules.capability_probe import CapabilityProbeResult
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
)


def registry():
    return CapabilityRegistry({Capability.ASIAIR_MONITORING})


def probe(status, observation=None):
    return CapabilityProbeResult(
        capability=Capability.ASIAIR_MONITORING,
        status=status,
        observation=observation,
    )


def test_reachable_observation_establishes_asiair_online():
    tracker = AsiairStateTracker()
    capabilities = registry()

    result = process_asiair_probe(
        probe_result=probe(CapabilityStatus.AVAILABLE, True),
        registry=capabilities,
        tracker=tracker,
    )

    assert result.observation_accepted
    assert result.asiair_state is AsiairState.ONLINE
    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )


def test_unreachable_before_establishment_is_not_lost():
    tracker = AsiairStateTracker()

    result = process_asiair_probe(
        probe_result=probe(CapabilityStatus.AVAILABLE, False),
        registry=registry(),
        tracker=tracker,
    )

    assert result.observation_accepted
    assert result.asiair_state is AsiairState.NOT_ESTABLISHED


def test_unreachable_after_establishment_becomes_lost():
    tracker = AsiairStateTracker()
    capabilities = registry()

    process_asiair_probe(
        probe_result=probe(CapabilityStatus.AVAILABLE, True),
        registry=capabilities,
        tracker=tracker,
    )

    result = process_asiair_probe(
        probe_result=probe(CapabilityStatus.AVAILABLE, False),
        registry=capabilities,
        tracker=tracker,
    )

    assert result.asiair_state is AsiairState.LOST


def test_unknown_monitoring_path_does_not_create_false_asiair_loss():
    tracker = AsiairStateTracker()
    capabilities = registry()

    process_asiair_probe(
        probe_result=probe(CapabilityStatus.AVAILABLE, True),
        registry=capabilities,
        tracker=tracker,
    )

    result = process_asiair_probe(
        probe_result=probe(CapabilityStatus.UNKNOWN),
        registry=capabilities,
        tracker=tracker,
    )

    assert not result.observation_accepted
    assert result.asiair_state is AsiairState.ONLINE
    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


def test_failed_monitoring_path_does_not_create_false_asiair_loss():
    tracker = AsiairStateTracker()
    capabilities = registry()

    process_asiair_probe(
        probe_result=probe(CapabilityStatus.AVAILABLE, True),
        registry=capabilities,
        tracker=tracker,
    )

    result = process_asiair_probe(
        probe_result=probe(CapabilityStatus.FAILED),
        registry=capabilities,
        tracker=tracker,
    )

    assert not result.observation_accepted
    assert result.asiair_state is AsiairState.ONLINE


def test_wrong_capability_is_rejected_without_state_change():
    tracker = AsiairStateTracker()
    capabilities = registry()

    wrong = CapabilityProbeResult(
        capability=Capability.OBSERVATORY_SAFETY_MONITORING,
        status=CapabilityStatus.AVAILABLE,
        observation=True,
    )

    with pytest.raises(ValueError):
        process_asiair_probe(
            probe_result=wrong,
            registry=capabilities,
            tracker=tracker,
        )

    assert tracker.state is AsiairState.NOT_ESTABLISHED
    assert (
        capabilities.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )
