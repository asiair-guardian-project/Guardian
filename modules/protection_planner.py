"""Guardian 1.0 hardware-neutral protection response planning."""

from modules.guardian_types import ProtectionAction


def build_protection_plan() -> list[ProtectionAction]:
    """Plan immediate Safety Power shutdown without mount communication.

    Emergency shutdown requires no mount telemetry or STOP capability.
    """
    return [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]
