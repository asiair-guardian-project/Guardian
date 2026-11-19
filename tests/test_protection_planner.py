from modules.guardian_types import ProtectionAction
from modules.protection_planner import build_protection_plan


def test_emergency_plan_shuts_down_all_three_power_roles():
    assert build_protection_plan() == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]


def test_emergency_plan_never_requests_independent_mount_commands():
    plan = build_protection_plan()

    assert ProtectionAction.REQUEST_MOUNT_STOP not in plan
    assert ProtectionAction.VERIFY_MOUNT_STOP not in plan
