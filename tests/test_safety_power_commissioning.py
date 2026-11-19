from datetime import datetime, timezone

import pytest

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    evaluate_commissioning_evidence,
)
from modules.guardian_types import (
    SafetyPowerResult,
    SafetyPowerRole,
)
from modules.safety_power import (
    GuardianSafetyResources,
    SafetyPowerEndpoint,
    SafetyPowerEndpointEffects,
    SafetyPowerEndpointRequirements,
    SafetyPowerResourceEffects,
    SafetyPowerTopology,
    validate_safety_power_topology,
)
from modules.safety_power_commissioning import (
    SafetyPowerPhysicalObservation,
    evaluate_safety_power_role_commissioning,
)


NOW = datetime.now(timezone.utc)

AIR = SafetyPowerEndpoint("controller", "air")
MOUNT = SafetyPowerEndpoint("controller", "mount")
ACCESSORIES = SafetyPowerEndpoint("controller", "accessories")

TOPOLOGY = SafetyPowerTopology(
    {
        SafetyPowerRole.ASIAIR: AIR,
        SafetyPowerRole.MOUNT: MOUNT,
        SafetyPowerRole.ACCESSORIES: ACCESSORIES,
    }
)

EFFECTS = {
    AIR: SafetyPowerEndpointEffects(
        AIR,
        frozenset({SafetyPowerRole.ASIAIR}),
    ),
    MOUNT: SafetyPowerEndpointEffects(
        MOUNT,
        frozenset({SafetyPowerRole.MOUNT}),
    ),
    ACCESSORIES: SafetyPowerEndpointEffects(
        ACCESSORIES,
        frozenset({SafetyPowerRole.ACCESSORIES}),
    ),
}

REQUIREMENTS = {
    AIR: SafetyPowerEndpointRequirements(AIR, frozenset()),
    MOUNT: SafetyPowerEndpointRequirements(MOUNT, frozenset()),
    ACCESSORIES: SafetyPowerEndpointRequirements(ACCESSORIES, frozenset()),
}

RESOURCE_EFFECTS = {
    AIR: SafetyPowerResourceEffects(AIR, frozenset()),
    MOUNT: SafetyPowerResourceEffects(MOUNT, frozenset()),
    ACCESSORIES: SafetyPowerResourceEffects(ACCESSORIES, frozenset()),
}

VALIDATION = validate_safety_power_topology(
    TOPOLOGY,
    EFFECTS,
    REQUIREMENTS,
    RESOURCE_EFFECTS,
    GuardianSafetyResources(frozenset()),
)


def observation(
    endpoint,
    *,
    result=SafetyPowerResult.VERIFIED_OFF,
    unpowered_roles=frozenset(),
    guardian_alive=True,
):
    return SafetyPowerPhysicalObservation(
        endpoint=endpoint,
        controller_result=result,
        observed_unpowered_roles=unpowered_roles,
        guardian_remained_operational=guardian_alive,
        observed_at=NOW,
    )


def test_asiair_physical_shutdown_verifies_role():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.ASIAIR,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            AIR,
            unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
        ),
    )

    assert evidence.check is CommissioningCheck.ASIAIR_SAFETY_POWER
    assert evidence.passed
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


def test_mount_physical_shutdown_verifies_role():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.MOUNT,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            MOUNT,
            unpowered_roles=frozenset({SafetyPowerRole.MOUNT}),
        ),
    )

    assert evidence.check is CommissioningCheck.MOUNT_SAFETY_POWER
    assert evidence.passed


def test_wrong_endpoint_does_not_verify_role():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.ASIAIR,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            MOUNT,
            unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
        ),
    )

    assert not evidence.passed


def test_controller_failure_does_not_verify_role():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.ASIAIR,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            AIR,
            result=SafetyPowerResult.FAILED,
            unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
        ),
    )

    assert not evidence.passed


def test_controller_success_without_physical_shutdown_does_not_verify():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.ASIAIR,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(AIR),
    )

    assert not evidence.passed


def test_guardian_loss_does_not_verify_role():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.MOUNT,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            MOUNT,
            unpowered_roles=frozenset({SafetyPowerRole.MOUNT}),
            guardian_alive=False,
        ),
    )

    assert not evidence.passed


def test_accessories_physical_shutdown_verifies_role():
    evidence = evaluate_safety_power_role_commissioning(
        SafetyPowerRole.ACCESSORIES,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            ACCESSORIES,
            unpowered_roles=frozenset({SafetyPowerRole.ACCESSORIES}),
        ),
    )

    assert evidence.check is CommissioningCheck.ACCESSORIES_SAFETY_POWER
    assert evidence.passed


def test_guardian_survival_requires_all_three_required_shutdown_tests():
    from modules.safety_power_commissioning import (
        evaluate_guardian_survival_commissioning,
    )

    evidence = evaluate_guardian_survival_commissioning(
        (
            observation(
                AIR,
                unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
            ),
            observation(
                MOUNT,
                unpowered_roles=frozenset({SafetyPowerRole.MOUNT}),
            ),
            observation(
                ACCESSORIES,
                unpowered_roles=frozenset({SafetyPowerRole.ACCESSORIES}),
            ),
        ),
        topology=TOPOLOGY,
        validation=VALIDATION,
    )

    assert evidence.check is CommissioningCheck.GUARDIAN_SURVIVAL
    assert evidence.passed
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


def test_guardian_survival_fails_when_required_role_not_tested():
    from modules.safety_power_commissioning import (
        evaluate_guardian_survival_commissioning,
    )

    evidence = evaluate_guardian_survival_commissioning(
        (
            observation(
                AIR,
                unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
            ),
        ),
        topology=TOPOLOGY,
        validation=VALIDATION,
    )

    assert not evidence.passed


def test_guardian_survival_fails_if_guardian_dies_during_any_test():
    from modules.safety_power_commissioning import (
        evaluate_guardian_survival_commissioning,
    )

    evidence = evaluate_guardian_survival_commissioning(
        (
            observation(
                AIR,
                unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
            ),
            observation(
                MOUNT,
                unpowered_roles=frozenset({SafetyPowerRole.MOUNT}),
                guardian_alive=False,
            ),
        ),
        topology=TOPOLOGY,
        validation=VALIDATION,
    )

    assert not evidence.passed


def test_guardian_survival_requires_observations():
    from modules.safety_power_commissioning import (
        evaluate_guardian_survival_commissioning,
    )

    with pytest.raises(ValueError):
        evaluate_guardian_survival_commissioning(
            (),
            topology=TOPOLOGY,
            validation=VALIDATION,
        )


def test_simultaneous_paths_verify_when_all_are_available_together():
    from modules.safety_power_commissioning import (
        SimultaneousPathObservation,
        evaluate_simultaneous_paths_commissioning,
    )

    evidence = evaluate_simultaneous_paths_commissioning(
        SimultaneousPathObservation(
            observatory_safety_available=True,
            asiair_monitoring_available=True,
            safety_power_control_available=True,
            observed_at=NOW,
        )
    )

    assert evidence.check is CommissioningCheck.SIMULTANEOUS_PATHS
    assert evidence.passed
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


@pytest.mark.parametrize(
    "observatory,asiair,power",
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (False, False, True),
        (False, True, False),
        (True, False, False),
        (False, False, False),
    ],
)
def test_simultaneous_paths_fail_if_any_required_path_is_unavailable(
    observatory,
    asiair,
    power,
):
    from modules.safety_power_commissioning import (
        SimultaneousPathObservation,
        evaluate_simultaneous_paths_commissioning,
    )

    evidence = evaluate_simultaneous_paths_commissioning(
        SimultaneousPathObservation(
            observatory_safety_available=observatory,
            asiair_monitoring_available=asiair,
            safety_power_control_available=power,
            observed_at=NOW,
        )
    )

    assert not evidence.passed
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.FAILED
    )


def test_guardian_survival_fails_without_accessories_shutdown_evidence():
    from modules.safety_power_commissioning import (
        evaluate_guardian_survival_commissioning,
    )

    evidence = evaluate_guardian_survival_commissioning(
        (
            observation(
                AIR,
                unpowered_roles=frozenset({SafetyPowerRole.ASIAIR}),
            ),
            observation(
                MOUNT,
                unpowered_roles=frozenset({SafetyPowerRole.MOUNT}),
            ),
        ),
        topology=TOPOLOGY,
        validation=VALIDATION,
    )

    assert VALIDATION.valid
    assert not evidence.passed
    assert evidence.observations["asiair_shutdown_proven"]
    assert evidence.observations["mount_shutdown_proven"]
    assert not evidence.observations["accessories_shutdown_proven"]


@pytest.mark.parametrize(
    "result",
    [
        SafetyPowerResult.SIMULATED,
        SafetyPowerResult.COMMANDED_UNVERIFIED,
        SafetyPowerResult.FAILED,
    ],
)
@pytest.mark.parametrize(
    "role,endpoint",
    [
        (SafetyPowerRole.ASIAIR, AIR),
        (SafetyPowerRole.MOUNT, MOUNT),
        (SafetyPowerRole.ACCESSORIES, ACCESSORIES),
    ],
)
def test_unverified_controller_results_never_verify_role(
    result, role, endpoint
):
    evidence = evaluate_safety_power_role_commissioning(
        role,
        topology=TOPOLOGY,
        validation=VALIDATION,
        observation=observation(
            endpoint,
            result=result,
            unpowered_roles=frozenset({role}),
        ),
    )

    assert VALIDATION.valid
    assert not evidence.passed
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.FAILED
    )


@pytest.mark.parametrize(
    "result",
    [
        SafetyPowerResult.SIMULATED,
        SafetyPowerResult.COMMANDED_UNVERIFIED,
        SafetyPowerResult.FAILED,
    ],
)
@pytest.mark.parametrize(
    "role,endpoint",
    [
        (SafetyPowerRole.ASIAIR, AIR),
        (SafetyPowerRole.MOUNT, MOUNT),
        (SafetyPowerRole.ACCESSORIES, ACCESSORIES),
    ],
)
def test_unverified_controller_results_never_verify_survival(
    result, role, endpoint
):
    from modules.safety_power_commissioning import (
        evaluate_guardian_survival_commissioning,
    )

    endpoints = {
        SafetyPowerRole.ASIAIR: AIR,
        SafetyPowerRole.MOUNT: MOUNT,
        SafetyPowerRole.ACCESSORIES: ACCESSORIES,
    }

    observations = tuple(
        observation(
            current_endpoint,
            result=(
                result
                if current_role is role
                else SafetyPowerResult.VERIFIED_OFF
            ),
            unpowered_roles=frozenset({current_role}),
        )
        for current_role, current_endpoint in endpoints.items()
    )

    evidence = evaluate_guardian_survival_commissioning(
        observations,
        topology=TOPOLOGY,
        validation=VALIDATION,
    )

    assert VALIDATION.valid
    assert not evidence.passed
    assert not evidence.observations[
        {
            SafetyPowerRole.ASIAIR: "asiair_shutdown_proven",
            SafetyPowerRole.MOUNT: "mount_shutdown_proven",
            SafetyPowerRole.ACCESSORIES: "accessories_shutdown_proven",
        }[role]
    ]
