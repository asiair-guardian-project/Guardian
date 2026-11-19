from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    MountMotionState,
)
from modules.mount_capability_probe import probe_mount_capabilities


class FakeMount:
    def __init__(self, *, capabilities, motion):
        self.capabilities = frozenset(capabilities)
        self.motion = motion
        self.query_calls = 0
        self.stop_calls = 0
        self.verify_calls = 0
        self.recovery_calls = 0

    def query_motion(self):
        self.query_calls += 1
        return self.motion

    def request_stop(self):
        self.stop_calls += 1
        raise AssertionError("capability probe must not request STOP")

    def verify_stop(self):
        self.verify_calls += 1
        raise AssertionError("capability probe must not verify STOP")

    def recover_connection(self):
        self.recovery_calls += 1
        raise AssertionError("capability probe must not invoke recovery")


WAVE_CAPABILITIES = {
    Capability.INDEPENDENT_MOUNT_MOTION,
    Capability.INDEPENDENT_MOUNT_STOP,
    Capability.MOUNT_STOP_VERIFICATION,
    Capability.MOUNT_CONNECTION_RECOVERY,
}


def result_map(results):
    return {
        result.capability: result
        for result in results
    }


def test_healthy_mount_path_marks_declared_capabilities_available():
    mount = FakeMount(
        capabilities=WAVE_CAPABILITIES,
        motion=MountMotionState.STATIONARY,
    )

    results = probe_mount_capabilities(mount)

    assert {result.capability for result in results} == WAVE_CAPABILITIES

    for result in results:
        assert result.status is CapabilityStatus.AVAILABLE

    assert mount.query_calls == 1
    assert mount.stop_calls == 0
    assert mount.verify_calls == 0
    assert mount.recovery_calls == 0


def test_moving_mount_is_still_a_healthy_capability_path():
    mount = FakeMount(
        capabilities=WAVE_CAPABILITIES,
        motion=MountMotionState.MOVING,
    )

    results = probe_mount_capabilities(mount)
    by_capability = result_map(results)

    assert all(
        result.status is CapabilityStatus.AVAILABLE
        for result in results
    )
    assert (
        by_capability[Capability.INDEPENDENT_MOUNT_MOTION].observation
        is MountMotionState.MOVING
    )


def test_unknown_motion_does_not_claim_mount_capabilities_available():
    mount = FakeMount(
        capabilities=WAVE_CAPABILITIES,
        motion=MountMotionState.UNKNOWN,
    )

    results = probe_mount_capabilities(mount)

    assert all(
        result.status is CapabilityStatus.UNKNOWN
        for result in results
    )

    assert mount.query_calls == 1
    assert mount.stop_calls == 0
    assert mount.verify_calls == 0
    assert mount.recovery_calls == 0


def test_probe_only_reports_capabilities_declared_by_adapter():
    capabilities = {
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
    }

    mount = FakeMount(
        capabilities=capabilities,
        motion=MountMotionState.STATIONARY,
    )

    results = probe_mount_capabilities(mount)

    assert {result.capability for result in results} == capabilities


def test_probe_exception_reports_unknown_without_destructive_actions():
    class BrokenMount(FakeMount):
        def query_motion(self):
            self.query_calls += 1
            raise RuntimeError("mount communication failed")

    mount = BrokenMount(
        capabilities=WAVE_CAPABILITIES,
        motion=MountMotionState.STATIONARY,
    )

    results = probe_mount_capabilities(mount)

    assert all(
        result.status is CapabilityStatus.UNKNOWN
        for result in results
    )

    assert all(
        "mount communication failed" in result.detail
        for result in results
    )

    assert mount.stop_calls == 0
    assert mount.verify_calls == 0
    assert mount.recovery_calls == 0
