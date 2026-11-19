import pytest

from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import Capability, CapabilityStatus


def test_available_probe_can_report_negative_device_observation():
    result = CapabilityProbeResult(
        capability=Capability.ASIAIR_MONITORING,
        status=CapabilityStatus.AVAILABLE,
        observation=False,
        detail="ASIAIR did not respond to reachability test",
    )

    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation is False


def test_available_probe_can_report_positive_device_observation():
    result = CapabilityProbeResult(
        capability=Capability.ASIAIR_MONITORING,
        status=CapabilityStatus.AVAILABLE,
        observation=True,
    )

    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation is True


def test_failed_capability_is_distinct_from_negative_observation():
    result = CapabilityProbeResult(
        capability=Capability.SAFETY_POWER_CONTROL,
        status=CapabilityStatus.FAILED,
        observation=None,
        detail="controller command path failed",
    )

    assert result.status is CapabilityStatus.FAILED
    assert result.observation is None


def test_unknown_capability_can_have_no_observation():
    result = CapabilityProbeResult(
        capability=Capability.OBSERVATORY_SAFETY_MONITORING,
        status=CapabilityStatus.UNKNOWN,
        observation=None,
    )

    assert result.status is CapabilityStatus.UNKNOWN


def test_probe_cannot_mark_configured_capability_unavailable():
    with pytest.raises(ValueError):
        CapabilityProbeResult(
            capability=Capability.INDEPENDENT_MOUNT_STOP,
            status=CapabilityStatus.UNAVAILABLE,
        )
