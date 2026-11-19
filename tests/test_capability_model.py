from modules.capability_model import (
    REQUIRED_CAPABILITIES,
    installation_ready,
    protection_ready,
    unavailable_required_capabilities,
)
from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    CommissioningStatus,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.guardian_types import Capability, CapabilityStatus


def all_required_available():
    return {
        capability: CapabilityStatus.AVAILABLE
        for capability in REQUIRED_CAPABILITIES
    }


def test_all_required_capabilities_available_is_ready():
    assert protection_ready(all_required_available()) is True


def test_required_capability_unavailable_is_not_ready():
    statuses = all_required_available()
    statuses[Capability.SAFETY_POWER_CONTROL] = CapabilityStatus.UNAVAILABLE
    assert protection_ready(statuses) is False


def test_required_capability_unknown_is_not_ready():
    statuses = all_required_available()
    statuses[Capability.OBSERVATORY_SAFETY_MONITORING] = CapabilityStatus.UNKNOWN
    assert protection_ready(statuses) is False


def test_required_capability_failed_is_not_ready():
    statuses = all_required_available()
    statuses[Capability.ASIAIR_MONITORING] = CapabilityStatus.FAILED
    assert protection_ready(statuses) is False


def test_missing_required_capability_is_not_ready():
    statuses = all_required_available()
    del statuses[Capability.SAFETY_POWER_CONTROL]
    assert protection_ready(statuses) is False


def test_enhanced_capability_unavailable_does_not_block_readiness():
    statuses = all_required_available()
    statuses[Capability.INDEPENDENT_MOUNT_STOP] = CapabilityStatus.UNAVAILABLE
    assert protection_ready(statuses) is True


def test_reports_exact_required_capabilities_not_ready():
    statuses = all_required_available()
    statuses[Capability.SAFETY_POWER_CONTROL] = CapabilityStatus.FAILED
    statuses[Capability.ASIAIR_MONITORING] = CapabilityStatus.UNKNOWN

    assert unavailable_required_capabilities(statuses) == {
        Capability.SAFETY_POWER_CONTROL,
        Capability.ASIAIR_MONITORING,
    }

def commissioned_status(fingerprint="config-a"):
    return CommissioningStatus(
        {
            check: CommissioningResult.VERIFIED
            for check in REQUIRED_COMMISSIONING_CHECKS
        },
        configuration_fingerprint=fingerprint,
    )


def test_commissioned_matching_configuration_and_capabilities_is_ready():
    assert installation_ready(
        commissioned_status(),
        "config-a",
        all_required_available(),
    )


def test_changed_configuration_is_not_ready():
    assert not installation_ready(
        commissioned_status("config-a"),
        "config-b",
        all_required_available(),
    )


def test_incomplete_commissioning_is_not_ready():
    results = {
        check: CommissioningResult.VERIFIED
        for check in REQUIRED_COMMISSIONING_CHECKS
    }
    results[CommissioningCheck.PROTECTION_LOGIC] = (
        CommissioningResult.NOT_TESTED
    )

    commissioning = CommissioningStatus(
        results,
        configuration_fingerprint="config-a",
    )

    assert not installation_ready(
        commissioning,
        "config-a",
        all_required_available(),
    )


def test_current_required_capability_loss_is_not_ready():
    statuses = all_required_available()
    statuses[Capability.SAFETY_POWER_CONTROL] = CapabilityStatus.FAILED

    assert not installation_ready(
        commissioned_status(),
        "config-a",
        statuses,
    )

