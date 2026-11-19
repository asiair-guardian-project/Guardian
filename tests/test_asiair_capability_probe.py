from modules.asiair_capability_probe import probe_asiair_monitoring
from modules.guardian_types import Capability, CapabilityStatus


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def is_reachable(self):
        if self.error is not None:
            raise self.error
        return self.result


def test_reachable_asiair_means_monitoring_path_available():
    result = probe_asiair_monitoring(FakeAdapter(result=True))

    assert result.capability is Capability.ASIAIR_MONITORING
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation is True


def test_unreachable_asiair_still_means_monitoring_path_available():
    result = probe_asiair_monitoring(FakeAdapter(result=False))

    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation is False


def test_monitoring_mechanism_failure_is_unknown_capability():
    result = probe_asiair_monitoring(
        FakeAdapter(error=RuntimeError("ping unavailable"))
    )

    assert result.status is CapabilityStatus.UNKNOWN
    assert result.observation is None
