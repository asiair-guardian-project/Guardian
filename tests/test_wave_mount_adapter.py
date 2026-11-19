from modules.guardian_types import (
    Capability,
    MountMotionState,
    MountStopResult,
)
from modules.wave_interface import WaveCommunicationError
from modules.wave_mount_adapter import WaveMountAdapter


class FakeWave:
    def __init__(self, positions=None, stop_error=False):
        self.positions = {
            1: iter((positions or {}).get(1, [100, 100])),
            2: iter((positions or {}).get(2, [200, 200])),
        }
        self.stop_error = stop_error
        self.stop_requests = []

    def get_position(self, axis):
        return f"={next(self.positions[axis]):06X}"

    def stop(self, axis):
        self.stop_requests.append(axis)
        if self.stop_error:
            raise WaveCommunicationError("stop failed")
        return "="


def test_wave_advertises_level2_and_recovery_capabilities():
    adapter = WaveMountAdapter(
        wave=FakeWave(),
        recovery=lambda: True,
        sample_interval_seconds=0,
    )

    assert adapter.capabilities == frozenset({
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
        Capability.MOUNT_CONNECTION_RECOVERY,
    })


def test_query_motion_reports_stationary():
    adapter = WaveMountAdapter(
        wave=FakeWave({
            1: [100, 100],
            2: [200, 200],
        }),
        recovery=lambda: True,
        sample_interval_seconds=0,
    )

    assert adapter.query_motion() is MountMotionState.STATIONARY


def test_query_motion_reports_moving():
    adapter = WaveMountAdapter(
        wave=FakeWave({
            1: [100, 101],
            2: [200, 200],
        }),
        recovery=lambda: True,
        sample_interval_seconds=0,
    )

    assert adapter.query_motion() is MountMotionState.MOVING


def test_query_motion_reports_unknown_on_communication_failure():
    class BrokenWave:
        def get_position(self, axis):
            raise WaveCommunicationError("offline")

    adapter = WaveMountAdapter(
        wave=BrokenWave(),
        recovery=lambda: False,
        sample_interval_seconds=0,
    )

    assert adapter.query_motion() is MountMotionState.UNKNOWN


def test_request_stop_sends_stop_to_both_axes():
    wave = FakeWave()

    adapter = WaveMountAdapter(
        wave=wave,
        recovery=lambda: True,
        sample_interval_seconds=0,
    )

    assert adapter.request_stop() is MountStopResult.SUCCEEDED
    assert wave.stop_requests == [1, 2]


def test_request_stop_failure_is_failed():
    wave = FakeWave(stop_error=True)

    adapter = WaveMountAdapter(
        wave=wave,
        recovery=lambda: False,
        sample_interval_seconds=0,
    )

    assert adapter.request_stop() is MountStopResult.FAILED


def test_verify_stop_succeeds_when_stationary():
    adapter = WaveMountAdapter(
        wave=FakeWave({
            1: [100, 100],
            2: [200, 200],
        }),
        recovery=lambda: True,
        sample_interval_seconds=0,
    )

    assert adapter.verify_stop() is MountStopResult.SUCCEEDED


def test_verify_stop_fails_when_still_moving():
    adapter = WaveMountAdapter(
        wave=FakeWave({
            1: [100, 101],
            2: [200, 200],
        }),
        recovery=lambda: True,
        sample_interval_seconds=0,
    )

    assert adapter.verify_stop() is MountStopResult.FAILED


def test_recover_connection_delegates_to_recovery_service():
    calls = []

    def recovery():
        calls.append(True)
        return True

    adapter = WaveMountAdapter(
        wave=FakeWave(),
        recovery=recovery,
        sample_interval_seconds=0,
    )

    assert adapter.recover_connection() is True
    assert calls == [True]


def test_request_stop_attempts_both_axes_if_one_fails():
    class PartiallyBrokenWave:
        def __init__(self):
            self.stop_requests = []

        def stop(self, axis):
            self.stop_requests.append(axis)
            if axis == 1:
                raise WaveCommunicationError("axis 1 failed")
            return "="

    wave = PartiallyBrokenWave()

    adapter = WaveMountAdapter(
        wave=wave,
        recovery=lambda: False,
        sample_interval_seconds=0,
    )

    assert adapter.request_stop() is MountStopResult.FAILED
    assert wave.stop_requests == [1, 2]
