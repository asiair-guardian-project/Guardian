"""Guardian 1.0 Safety Power commissioning evidence."""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
)
from modules.guardian_types import (
    SafetyPowerResult,
    SafetyPowerRole,
)
from modules.safety_power import (
    SafetyPowerEndpoint,
    SafetyPowerTopology,
    SafetyPowerTopologyValidation,
)


@dataclass(frozen=True)
class SafetyPowerPhysicalObservation:
    """Observed result of a controlled physical endpoint test."""

    endpoint: SafetyPowerEndpoint
    controller_result: SafetyPowerResult
    observed_unpowered_roles: frozenset[SafetyPowerRole]
    guardian_remained_operational: bool
    observed_at: datetime


_ROLE_CHECKS = {
    SafetyPowerRole.ASIAIR: CommissioningCheck.ASIAIR_SAFETY_POWER,
    SafetyPowerRole.MOUNT: CommissioningCheck.MOUNT_SAFETY_POWER,
    SafetyPowerRole.ACCESSORIES: CommissioningCheck.ACCESSORIES_SAFETY_POWER,
}


def evaluate_safety_power_role_commissioning(
    role: SafetyPowerRole,
    *,
    topology: SafetyPowerTopology,
    validation: SafetyPowerTopologyValidation,
    observation: SafetyPowerPhysicalObservation,
) -> CommissioningEvidence:
    """Evaluate physical proof for one required Safety Power role."""

    if role not in _ROLE_CHECKS:
        raise ValueError(
            f"{role.name} is not a required Safety Power commissioning role"
        )

    endpoint = topology.endpoint_for(role)

    endpoint_matches = (
        endpoint is not None
        and observation.endpoint == endpoint
    )
    controller_succeeded = (
        observation.controller_result
        is SafetyPowerResult.VERIFIED_OFF
    )
    physical_role_unpowered = (
        role in observation.observed_unpowered_roles
    )

    passed = (
        validation.valid
        and endpoint_matches
        and controller_succeeded
        and physical_role_unpowered
        and observation.guardian_remained_operational
    )

    summary = (
        f"{role.name} Safety Power endpoint physically verified"
        if passed
        else f"{role.name} Safety Power endpoint was not physically verified"
    )

    details: Mapping[str, object] = {
        "controller_id": observation.endpoint.controller_id,
        "endpoint_id": observation.endpoint.endpoint_id,
        "topology_valid": validation.valid,
        "endpoint_matches": endpoint_matches,
        "controller_result": observation.controller_result.name,
        "physical_role_unpowered": physical_role_unpowered,
        "guardian_remained_operational": (
            observation.guardian_remained_operational
        ),
    }

    return CommissioningEvidence(
        check=_ROLE_CHECKS[role],
        completed=True,
        passed=passed,
        observed_at=observation.observed_at,
        summary=summary,
        observations=details,
    )


def evaluate_guardian_survival_commissioning(
    observations: tuple[SafetyPowerPhysicalObservation, ...],
    *,
    topology: SafetyPowerTopology,
    validation: SafetyPowerTopologyValidation,
) -> CommissioningEvidence:
    """Evaluate whether Guardian survived required Safety Power tests."""

    if not observations:
        raise ValueError(
            "Guardian survival commissioning requires observations"
        )

    required_roles = (
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
        SafetyPowerRole.ACCESSORIES,
    )

    proven_roles = set()

    for role in required_roles:
        endpoint = topology.endpoint_for(role)

        if endpoint is None:
            continue

        if any(
            observation.endpoint == endpoint
            and role in observation.observed_unpowered_roles
            and observation.controller_result
            is SafetyPowerResult.VERIFIED_OFF
            and observation.guardian_remained_operational
            for observation in observations
        ):
            proven_roles.add(role)

    all_required_roles_proven = all(
        role in proven_roles
        for role in required_roles
    )

    guardian_survived_all_observations = all(
        observation.guardian_remained_operational
        for observation in observations
    )

    passed = (
        validation.valid
        and all_required_roles_proven
        and guardian_survived_all_observations
    )

    summary = (
        "Guardian remained operational through required Safety Power tests"
        if passed
        else "Guardian survival was not verified through all required tests"
    )

    details: Mapping[str, object] = {
        "topology_valid": validation.valid,
        "asiair_shutdown_proven": (
            SafetyPowerRole.ASIAIR in proven_roles
        ),
        "mount_shutdown_proven": (
            SafetyPowerRole.MOUNT in proven_roles
        ),
        "accessories_shutdown_proven": (
            SafetyPowerRole.ACCESSORIES in proven_roles
        ),
        "guardian_survived_all_observations": (
            guardian_survived_all_observations
        ),
        "observation_count": len(observations),
    }

    return CommissioningEvidence(
        check=CommissioningCheck.GUARDIAN_SURVIVAL,
        completed=True,
        passed=passed,
        observed_at=max(
            observation.observed_at
            for observation in observations
        ),
        summary=summary,
        observations=details,
    )


@dataclass(frozen=True)
class SimultaneousPathObservation:
    """Availability of all required independent safety paths at one moment."""

    observatory_safety_available: bool
    asiair_monitoring_available: bool
    safety_power_control_available: bool
    observed_at: datetime


def evaluate_simultaneous_paths_commissioning(
    observation: SimultaneousPathObservation,
) -> CommissioningEvidence:
    """Verify that all required safety paths were available simultaneously."""

    passed = (
        observation.observatory_safety_available
        and observation.asiair_monitoring_available
        and observation.safety_power_control_available
    )

    summary = (
        "Required safety paths were simultaneously available"
        if passed
        else "Required safety paths were not simultaneously available"
    )

    details: Mapping[str, object] = {
        "observatory_safety_available": (
            observation.observatory_safety_available
        ),
        "asiair_monitoring_available": (
            observation.asiair_monitoring_available
        ),
        "safety_power_control_available": (
            observation.safety_power_control_available
        ),
    }

    return CommissioningEvidence(
        check=CommissioningCheck.SIMULTANEOUS_PATHS,
        completed=True,
        passed=passed,
        observed_at=observation.observed_at,
        summary=summary,
        observations=details,
    )
