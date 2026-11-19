from datetime import datetime, timedelta, timezone

import pytest

from modules.capability_probe import CapabilityProbeResult
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    RoofState,
)
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)
from modules.observatory_safety import ObservatorySafetyObservation


NOW = datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)
MAX_AGE = 10.0


def registry():
    return CapabilityRegistry(
        {Capability.OBSERVATORY_SAFETY_MONITORING}
    )


def observation(state, age_seconds=0):
    return ObservatorySafetyObservation(
        state=state,
        observed_at=NOW - timedelta(seconds=age_seconds),
    )


def probe(status, value=None):
    return CapabilityProbeResult(
        capability=Capability.OBSERVATORY_SAFETY_MONITORING,
        status=status,
        observation=value,
    )


def test_fresh_open_observation_is_accepted():
    coordinator = ObservatoryObservationCoordinator()
    capabilities = registry()

    result = coordinator.process_probe(
        probe_result=probe(
            CapabilityStatus.AVAILABLE,
            observation(RoofState.OPEN),
        ),
        registry=capabilities,
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert result.observation_accepted
    assert result.roof_state is RoofState.OPEN
    assert (
        capabilities.status(
            Capability.OBSERVATORY_SAFETY_MONITORING
        )
        is CapabilityStatus.AVAILABLE
    )


def test_fresh_closed_observation_is_accepted():
    coordinator = ObservatoryObservationCoordinator()

    result = coordinator.process_probe(
        probe_result=probe(
            CapabilityStatus.AVAILABLE,
            observation(RoofState.CLOSED),
        ),
        registry=registry(),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert result.roof_state is RoofState.CLOSED


def test_explicit_unknown_observation_is_accepted():
    coordinator = ObservatoryObservationCoordinator()

    result = coordinator.process_probe(
        probe_result=probe(
            CapabilityStatus.AVAILABLE,
            observation(RoofState.UNKNOWN),
        ),
        registry=registry(),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert result.observation_accepted
    assert result.roof_state is RoofState.UNKNOWN


def test_monitoring_failure_without_prior_observation_is_unknown():
    coordinator = ObservatoryObservationCoordinator()

    result = coordinator.process_probe(
        probe_result=probe(CapabilityStatus.UNKNOWN),
        registry=registry(),
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    assert not result.observation_accepted
    assert result.roof_state is RoofState.UNKNOWN


def test_monitoring_failure_does_not_invent_new_roof_observation():
    coordinator = ObservatoryObservationCoordinator()
    capabilities = registry()

    original = observation(RoofState.OPEN)

    coordinator.process_probe(
        probe_result=probe(
            CapabilityStatus.AVAILABLE,
            original,
        ),
        registry=capabilities,
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    result = coordinator.process_probe(
        probe_result=probe(CapabilityStatus.UNKNOWN),
        registry=capabilities,
        now=NOW + timedelta(seconds=5),
        max_age_seconds=MAX_AGE,
    )

    assert not result.observation_accepted
    assert coordinator.last_observation is original
    assert result.roof_state is RoofState.UNKNOWN
    assert (
        capabilities.status(
            Capability.OBSERVATORY_SAFETY_MONITORING
        )
        is CapabilityStatus.UNKNOWN
    )


def test_retained_observation_eventually_becomes_stale_unknown():
    coordinator = ObservatoryObservationCoordinator()
    capabilities = registry()

    coordinator.process_probe(
        probe_result=probe(
            CapabilityStatus.AVAILABLE,
            observation(RoofState.OPEN),
        ),
        registry=capabilities,
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    result = coordinator.process_probe(
        probe_result=probe(CapabilityStatus.UNKNOWN),
        registry=capabilities,
        now=NOW + timedelta(seconds=11),
        max_age_seconds=MAX_AGE,
    )

    assert result.roof_state is RoofState.UNKNOWN


def test_wrong_capability_is_rejected_without_changing_observation():
    coordinator = ObservatoryObservationCoordinator()
    capabilities = registry()

    original = observation(RoofState.CLOSED)

    coordinator.process_probe(
        probe_result=probe(
            CapabilityStatus.AVAILABLE,
            original,
        ),
        registry=capabilities,
        now=NOW,
        max_age_seconds=MAX_AGE,
    )

    wrong = CapabilityProbeResult(
        capability=Capability.ASIAIR_MONITORING,
        status=CapabilityStatus.AVAILABLE,
        observation=None,
    )

    with pytest.raises(ValueError):
        coordinator.process_probe(
            probe_result=wrong,
            registry=capabilities,
            now=NOW,
            max_age_seconds=MAX_AGE,
        )

    assert coordinator.last_observation is original
