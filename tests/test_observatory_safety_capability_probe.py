from datetime import datetime, timezone

from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    RoofState,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.observatory_safety_capability_probe import (
    probe_observatory_safety,
)


NOW = datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)


class FakeAdapter:
    def __init__(self, observation=None, error=None):
        self.observation = observation
        self.error = error

    def observe(self):
        if self.error is not None:
            raise self.error
        return self.observation


def observation(state):
    return ObservatorySafetyObservation(
        state=state,
        observed_at=NOW,
    )


def test_open_observation_means_monitoring_available():
    result = probe_observatory_safety(
        FakeAdapter(observation(RoofState.OPEN))
    )

    assert (
        result.capability
        is Capability.OBSERVATORY_SAFETY_MONITORING
    )
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation.state is RoofState.OPEN


def test_closed_observation_means_monitoring_available():
    result = probe_observatory_safety(
        FakeAdapter(observation(RoofState.CLOSED))
    )

    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation.state is RoofState.CLOSED


def test_explicit_unknown_can_come_from_working_monitor():
    result = probe_observatory_safety(
        FakeAdapter(observation(RoofState.UNKNOWN))
    )

    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation.state is RoofState.UNKNOWN


def test_monitoring_failure_does_not_invent_roof_state():
    result = probe_observatory_safety(
        FakeAdapter(error=RuntimeError("source unavailable"))
    )

    assert result.status is CapabilityStatus.UNKNOWN
    assert result.observation is None
