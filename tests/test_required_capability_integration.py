from modules.capability_model import protection_ready
from modules.capability_probe import CapabilityProbeResult
from modules.capability_probe_coordinator import apply_probe_results
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SessionState,
)
from modules.protection_evaluator import evaluate_protection_triggers


REQUIRED = {
    Capability.ASIAIR_MONITORING,
    Capability.OBSERVATORY_SAFETY_MONITORING,
    Capability.SAFETY_POWER_CONTROL,
}


def registry():
    return CapabilityRegistry(REQUIRED)


def result(capability, status):
    return CapabilityProbeResult(
        capability=capability,
        status=status,
    )


def available_results():
    return [
        result(
            Capability.ASIAIR_MONITORING,
            CapabilityStatus.AVAILABLE,
        ),
        result(
            Capability.OBSERVATORY_SAFETY_MONITORING,
            CapabilityStatus.AVAILABLE,
        ),
        result(
            Capability.SAFETY_POWER_CONTROL,
            CapabilityStatus.AVAILABLE,
        ),
    ]


def test_all_required_capabilities_available_is_protection_ready():
    capabilities = registry()

    apply_probe_results(
        registry=capabilities,
        results=available_results(),
    )

    assert protection_ready(capabilities.snapshot())


def test_each_required_capability_blocks_readiness_when_unknown():
    for capability in REQUIRED:
        capabilities = registry()
        results = available_results()

        results = [
            result(
                item.capability,
                (
                    CapabilityStatus.UNKNOWN
                    if item.capability is capability
                    else item.status
                ),
            )
            for item in results
        ]

        apply_probe_results(
            registry=capabilities,
            results=results,
        )

        assert not protection_ready(capabilities.snapshot())


def test_each_required_capability_blocks_readiness_when_failed():
    for capability in REQUIRED:
        capabilities = registry()
        results = available_results()

        results = [
            result(
                item.capability,
                (
                    CapabilityStatus.FAILED
                    if item.capability is capability
                    else item.status
                ),
            )
            for item in results
        ]

        apply_probe_results(
            registry=capabilities,
            results=results,
        )

        assert not protection_ready(capabilities.snapshot())


def test_probe_batch_is_atomic_when_one_result_is_invalid():
    capabilities = registry()

    before = capabilities.snapshot()

    invalid_batch = [
        result(
            Capability.ASIAIR_MONITORING,
            CapabilityStatus.AVAILABLE,
        ),
        result(
            Capability.OBSERVATORY_SAFETY_MONITORING,
            CapabilityStatus.AVAILABLE,
        ),
        result(
            Capability.INDEPENDENT_MOUNT_STOP,
            CapabilityStatus.AVAILABLE,
        ),
    ]

    try:
        apply_probe_results(
            registry=capabilities,
            results=invalid_batch,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid probe batch was accepted")

    assert capabilities.snapshot() == before


def test_active_imaging_triggers_when_required_capability_is_lost():
    for capability in REQUIRED:
        statuses = {
            item: CapabilityStatus.AVAILABLE
            for item in REQUIRED
        }
        statuses[capability] = CapabilityStatus.UNKNOWN

        triggers = evaluate_protection_triggers(
            session_state=SessionState.IMAGING_PERMITTED,
            roof_state=RoofState.OPEN,
            asiair_state=AsiairState.ONLINE,
            required_capability_statuses=list(statuses.values()),
        )

        assert (
            ProtectionTrigger.PROTECTION_CAPABILITY_LOST
            in triggers
        )


def test_all_required_capabilities_available_does_not_trigger_loss():
    statuses = {
        capability: CapabilityStatus.AVAILABLE
        for capability in REQUIRED
    }

    triggers = evaluate_protection_triggers(
        session_state=SessionState.IMAGING_PERMITTED,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        required_capability_statuses=list(statuses.values()),
    )

    assert (
        ProtectionTrigger.PROTECTION_CAPABILITY_LOST
        not in triggers
    )
