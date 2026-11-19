"""Shared state and result types for Guardian 1.0.

These enums define the vocabulary exchanged between Guardian Core and
hardware/service adapters. They contain no hardware-specific behavior.
"""

from enum import Enum, auto


class SessionState(Enum):
    DISARMED = auto()
    WAITING_FOR_ROOF = auto()
    WAITING_FOR_PROTECTION = auto()
    IMAGING_PERMITTED = auto()
    ABORTED = auto()


class RoofState(Enum):
    OPEN = auto()
    CLOSED = auto()
    UNKNOWN = auto()


class AsiairState(Enum):
    NOT_ESTABLISHED = auto()
    ONLINE = auto()
    LOST = auto()


class MountMotionState(Enum):
    MOVING = auto()
    STATIONARY = auto()
    UNKNOWN = auto()
    UNAVAILABLE = auto()


class CapabilityStatus(Enum):
    AVAILABLE = auto()
    UNAVAILABLE = auto()
    UNKNOWN = auto()
    FAILED = auto()


class ProtectionTrigger(Enum):
    ROOF_CLOSED = auto()
    ASIAIR_LOST = auto()
    PROTECTION_CAPABILITY_LOST = auto()
    # Guardian stopped or restarted while an operator-armed session was
    # recorded. Nothing watched the roof in the gap, so the rig is powered
    # off and the operator sorts it out afterwards.
    RESTART_WHILE_ARMED = auto()
    # UPS is running on battery and has reached the low-battery threshold
    # during an active session. The rig is powered off before the UPS dies.
    UPS_LOW_BATTERY = auto()
    # An unexpected error escaped a Guardian cycle while a session was armed
    # or active. Guardian can no longer vouch for its own protection, so the
    # rig is powered off first and the fault is investigated afterwards.
    INTERNAL_FAULT = auto()


class SafetyPowerRole(Enum):
    ASIAIR = auto()
    MOUNT = auto()
    ACCESSORIES = auto()
    GUARDIAN_HOST = auto()


class SafetyPowerState(Enum):
    """Observed state of a Safety Power endpoint."""

    ON = auto()
    OFF = auto()
    UNKNOWN = auto()


class SafetyPowerResult(Enum):
    VERIFIED_OFF = auto()
    COMMANDED_UNVERIFIED = auto()
    FAILED = auto()
    SIMULATED = auto()


class Capability(Enum):
    # Required Guardian 1.0 capabilities
    ASIAIR_MONITORING = auto()
    OBSERVATORY_SAFETY_MONITORING = auto()
    SAFETY_POWER_CONTROL = auto()

    # Enhanced capabilities
    SAFETY_POWER_STATE_VERIFICATION = auto()
    INDEPENDENT_MOUNT_MOTION = auto()
    INDEPENDENT_MOUNT_STOP = auto()
    MOUNT_STOP_VERIFICATION = auto()
    MOUNT_CONNECTION_RECOVERY = auto()
    INDEPENDENT_MOUNT_POSITION = auto()
    UPS_MONITORING = auto()
    ACCESSORY_SAFETY_POWER_CONTROL = auto()


class ProtectionAction(Enum):
    """Hardware-neutral actions requested by Guardian Core."""

    REQUEST_MOUNT_STOP = auto()
    VERIFY_MOUNT_STOP = auto()
    SAFETY_POWER_OFF_ASIAIR = auto()
    SAFETY_POWER_OFF_MOUNT = auto()
    SAFETY_POWER_OFF_ACCESSORIES = auto()


class MountStopResult(Enum):
    """Outcome of an independent protective mount STOP attempt."""

    SUCCEEDED = auto()
    FAILED = auto()
    TIMED_OUT = auto()
    UNVERIFIED = auto()
