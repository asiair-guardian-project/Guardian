from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    MountMotionState,
    ProtectionTrigger,
    RoofState,
    SafetyPowerResult,
    SessionState,
)


def test_guardian_1_0_core_types_exist():
    assert SessionState.ABORTED
    assert RoofState.UNKNOWN
    assert AsiairState.NOT_ESTABLISHED
    assert MountMotionState.UNAVAILABLE
    assert CapabilityStatus.FAILED
    assert ProtectionTrigger.PROTECTION_CAPABILITY_LOST
    assert SafetyPowerResult.COMMANDED_UNVERIFIED
    assert Capability.SAFETY_POWER_CONTROL


def test_unknown_and_unavailable_are_distinct():
    assert MountMotionState.UNKNOWN is not MountMotionState.UNAVAILABLE
    assert CapabilityStatus.UNKNOWN is not CapabilityStatus.UNAVAILABLE


def test_protection_action_types_exist():
    from modules.guardian_types import ProtectionAction

    assert ProtectionAction.REQUEST_MOUNT_STOP
    assert ProtectionAction.VERIFY_MOUNT_STOP
    assert ProtectionAction.SAFETY_POWER_OFF_ASIAIR
    assert ProtectionAction.SAFETY_POWER_OFF_MOUNT


def test_mount_stop_result_types_exist():
    from modules.guardian_types import MountStopResult

    assert MountStopResult.SUCCEEDED
    assert MountStopResult.FAILED
    assert MountStopResult.TIMED_OUT
    assert MountStopResult.UNVERIFIED
