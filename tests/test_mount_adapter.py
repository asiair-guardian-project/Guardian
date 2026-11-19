from modules.guardian_types import Capability, MountMotionState, MountStopResult


class Level1Mount:
    capabilities = frozenset({
        Capability.INDEPENDENT_MOUNT_STOP,
    })

    def request_stop(self):
        return MountStopResult.UNVERIFIED


class Level2Mount:
    capabilities = frozenset({
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
    })

    def query_motion(self):
        return MountMotionState.STATIONARY

    def request_stop(self):
        return MountStopResult.SUCCEEDED

    def verify_stop(self):
        return MountStopResult.SUCCEEDED


def test_level1_provides_stop_only():
    mount = Level1Mount()

    assert mount.capabilities == frozenset({
        Capability.INDEPENDENT_MOUNT_STOP,
    })
    assert mount.request_stop() is MountStopResult.UNVERIFIED
    assert not hasattr(mount, "query_motion")
    assert not hasattr(mount, "verify_stop")


def test_level2_supports_motion_stop_and_verification():
    mount = Level2Mount()

    assert Capability.INDEPENDENT_MOUNT_MOTION in mount.capabilities
    assert Capability.INDEPENDENT_MOUNT_STOP in mount.capabilities
    assert Capability.MOUNT_STOP_VERIFICATION in mount.capabilities
    assert mount.query_motion() is MountMotionState.STATIONARY
    assert mount.request_stop() is MountStopResult.SUCCEEDED
    assert mount.verify_stop() is MountStopResult.SUCCEEDED
