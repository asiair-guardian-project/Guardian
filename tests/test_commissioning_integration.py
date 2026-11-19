from datetime import datetime, timedelta, timezone

from modules.asiair_commissioning import (
    AsiairMonitoringObservation,
    evaluate_asiair_monitoring_commissioning,
)
from modules.commissioning_coordinator import assemble_commissioning_status
from modules.guardian_types import (
    RoofState,
    SafetyPowerResult,
    SafetyPowerRole,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.observatory_safety_commissioning import (
    evaluate_observatory_safety_commissioning,
)
from modules.protection_logic_commissioning import (
    evaluate_protection_logic_commissioning,
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
    SimultaneousPathObservation,
    evaluate_guardian_survival_commissioning,
    evaluate_safety_power_role_commissioning,
    evaluate_simultaneous_paths_commissioning,
)


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def test_real_commissioning_procedures_authorize_configuration():
    air_endpoint = SafetyPowerEndpoint("controller", "air")
    mount_endpoint = SafetyPowerEndpoint("controller", "mount")
    accessories_endpoint = SafetyPowerEndpoint("controller", "accessories")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: air_endpoint,
            SafetyPowerRole.MOUNT: mount_endpoint,
            SafetyPowerRole.ACCESSORIES: accessories_endpoint,
        }
    )

    effects = {
        air_endpoint: SafetyPowerEndpointEffects(
            air_endpoint,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount_endpoint: SafetyPowerEndpointEffects(
            mount_endpoint,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
        accessories_endpoint: SafetyPowerEndpointEffects(
            accessories_endpoint,
            frozenset({SafetyPowerRole.ACCESSORIES}),
        ),
    }

    requirements = {
        air_endpoint: SafetyPowerEndpointRequirements(
            air_endpoint,
            frozenset(),
        ),
        mount_endpoint: SafetyPowerEndpointRequirements(
            mount_endpoint,
            frozenset(),
        ),
        accessories_endpoint: SafetyPowerEndpointRequirements(
            accessories_endpoint,
            frozenset(),
        ),
    }

    resource_effects = {
        air_endpoint: SafetyPowerResourceEffects(
            air_endpoint,
            frozenset(),
        ),
        mount_endpoint: SafetyPowerResourceEffects(
            mount_endpoint,
            frozenset(),
        ),
        accessories_endpoint: SafetyPowerResourceEffects(
            accessories_endpoint,
            frozenset(),
        ),
    }

    validation = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
    )

    air_power_observation = SafetyPowerPhysicalObservation(
        endpoint=air_endpoint,
        controller_result=SafetyPowerResult.VERIFIED_OFF,
        observed_unpowered_roles=frozenset(
            {SafetyPowerRole.ASIAIR}
        ),
        guardian_remained_operational=True,
        observed_at=NOW,
    )

    mount_power_observation = SafetyPowerPhysicalObservation(
        endpoint=mount_endpoint,
        controller_result=SafetyPowerResult.VERIFIED_OFF,
        observed_unpowered_roles=frozenset(
            {SafetyPowerRole.MOUNT}
        ),
        guardian_remained_operational=True,
        observed_at=NOW,
    )

    accessories_power_observation = SafetyPowerPhysicalObservation(
        endpoint=accessories_endpoint,
        controller_result=SafetyPowerResult.VERIFIED_OFF,
        observed_unpowered_roles=frozenset(
            {SafetyPowerRole.ACCESSORIES}
        ),
        guardian_remained_operational=True,
        observed_at=NOW,
    )

    evidence = [
        evaluate_asiair_monitoring_commissioning(
            (
                AsiairMonitoringObservation(False, NOW),
                AsiairMonitoringObservation(
                    True,
                    NOW + timedelta(seconds=1),
                ),
            )
        ),
        evaluate_observatory_safety_commissioning(
            (
                ObservatorySafetyObservation(
                    RoofState.OPEN,
                    NOW - timedelta(seconds=1),
                ),
                ObservatorySafetyObservation(
                    RoofState.CLOSED,
                    NOW - timedelta(seconds=2),
                ),
                ObservatorySafetyObservation(
                    RoofState.OPEN,
                    NOW - timedelta(seconds=60),
                ),
            ),
            now=NOW,
            max_age_seconds=30.0,
        ),
        evaluate_safety_power_role_commissioning(
            SafetyPowerRole.ASIAIR,
            topology=topology,
            validation=validation,
            observation=air_power_observation,
        ),
        evaluate_safety_power_role_commissioning(
            SafetyPowerRole.MOUNT,
            topology=topology,
            validation=validation,
            observation=mount_power_observation,
        ),
        evaluate_safety_power_role_commissioning(
            SafetyPowerRole.ACCESSORIES,
            topology=topology,
            validation=validation,
            observation=accessories_power_observation,
        ),
        evaluate_guardian_survival_commissioning(
            (
                air_power_observation,
                mount_power_observation,
                accessories_power_observation,
            ),
            topology=topology,
            validation=validation,
        ),
        evaluate_simultaneous_paths_commissioning(
            SimultaneousPathObservation(
                observatory_safety_available=True,
                asiair_monitoring_available=True,
                safety_power_control_available=True,
                observed_at=NOW,
            )
        ),
        evaluate_protection_logic_commissioning(
            observed_at=NOW,
        ),
    ]

    status = assemble_commissioning_status(
        configuration_fingerprint="commissioned-installation",
        evidence=evidence,
    )

    assert len(evidence) == 8
    assert all(item.passed for item in evidence)
    assert status.commissioned
    assert status.unresolved_checks == frozenset()
    assert status.valid_for_configuration(
        "commissioned-installation"
    )
    assert not status.valid_for_configuration(
        "different-installation"
    )
