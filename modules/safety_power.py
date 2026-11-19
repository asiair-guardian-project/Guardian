"""Guardian 1.0 Safety Power model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyPowerEndpoint:
    """An independently controllable endpoint on a Safety Power Controller."""

    controller_id: str
    endpoint_id: str

    def __post_init__(self) -> None:
        if not self.controller_id.strip():
            raise ValueError("controller_id must not be empty")
        if not self.endpoint_id.strip():
            raise ValueError("endpoint_id must not be empty")


from collections.abc import Mapping

from modules.guardian_types import SafetyPowerRole


@dataclass(frozen=True)
class SafetyPowerTopology:
    """Maps Guardian logical power roles to physical Safety Power Endpoints."""

    role_endpoints: Mapping[SafetyPowerRole, SafetyPowerEndpoint]

    def endpoint_for(self, role: SafetyPowerRole) -> SafetyPowerEndpoint | None:
        return self.role_endpoints.get(role)

    def endpoints_for_roles(
        self,
        roles: set[SafetyPowerRole],
    ) -> frozenset[SafetyPowerEndpoint]:
        return frozenset(
            endpoint
            for role in roles
            if (endpoint := self.endpoint_for(role)) is not None
        )


@dataclass(frozen=True)
class SafetyPowerEndpointEffects:
    """Describes logical roles that lose power when an endpoint is switched off."""

    endpoint: SafetyPowerEndpoint
    affected_roles: frozenset[SafetyPowerRole]

    def affects(self, role: SafetyPowerRole) -> bool:
        return role in self.affected_roles

    @property
    def affects_guardian_host(self) -> bool:
        return self.affects(SafetyPowerRole.GUARDIAN_HOST)


REQUIRED_SHUTDOWN_ROLES = frozenset(
    {
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
        SafetyPowerRole.ACCESSORIES,
    }
)


def guardian_host_unsafe_endpoints(
    topology: SafetyPowerTopology,
    endpoint_effects: Mapping[SafetyPowerEndpoint, SafetyPowerEndpointEffects],
) -> frozenset[SafetyPowerEndpoint]:
    """Return required shutdown endpoints that would also power off Guardian."""

    required_endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SHUTDOWN_ROLES)
    )

    return frozenset(
        endpoint
        for endpoint in required_endpoints
        if (
            effects := endpoint_effects.get(endpoint)
        ) is not None
        and effects.affects_guardian_host
    )


@dataclass(frozen=True)
class SafetyPowerResource:
    """A resource required to execute a Safety Power operation."""

    kind: str
    resource_id: str

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("resource kind must not be empty")
        if not self.resource_id.strip():
            raise ValueError("resource_id must not be empty")


@dataclass(frozen=True)
class GuardianSafetyResources:
    """Resources Guardian requires to remain operational during protection."""

    required_resources: frozenset[SafetyPowerResource]


@dataclass(frozen=True)
class SafetyPowerEndpointRequirements:
    """Resources required through completion of an endpoint shutdown.

    Required resources must remain available while Guardian commands the
    endpoint and, where supported, verifies that the endpoint is off.
    """

    endpoint: SafetyPowerEndpoint
    required_resources: frozenset[SafetyPowerResource]


@dataclass(frozen=True)
class SafetyPowerResourceEffects:
    """Control resources made unavailable by switching an endpoint off."""

    endpoint: SafetyPowerEndpoint
    disabled_resources: frozenset[SafetyPowerResource]


def endpoints_disabling_guardian_resources(
    topology: SafetyPowerTopology,
    resource_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerResourceEffects,
    ],
    guardian_resources: GuardianSafetyResources,
) -> frozenset[SafetyPowerEndpoint]:
    """Return required endpoints that disable Guardian survival resources."""

    required_endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SHUTDOWN_ROLES)
    )

    unsafe = set()

    for endpoint in required_endpoints:
        effects = resource_effects.get(endpoint)

        if effects is None:
            continue

        if (
            effects.disabled_resources
            & guardian_resources.required_resources
        ):
            unsafe.add(endpoint)

    return frozenset(unsafe)


def endpoints_disabling_own_requirements(
    topology: SafetyPowerTopology,
    requirements: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointRequirements,
    ],
    resource_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerResourceEffects,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return required endpoints that disable resources they need themselves."""

    required_endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SHUTDOWN_ROLES)
    )

    unsafe = set()

    for endpoint in required_endpoints:
        endpoint_requirements = requirements.get(endpoint)
        endpoint_resource_effects = resource_effects.get(endpoint)

        if (
            endpoint_requirements is None
            or endpoint_resource_effects is None
        ):
            continue

        if (
            endpoint_requirements.required_resources
            & endpoint_resource_effects.disabled_resources
        ):
            unsafe.add(endpoint)

    return frozenset(unsafe)


class SafetyPowerDependencyError(ValueError):
    """Raised when no safe Safety Power endpoint order exists."""


def order_shutdown_endpoints_by_resources(
    endpoints: set[SafetyPowerEndpoint] | frozenset[SafetyPowerEndpoint],
    requirements: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointRequirements,
    ],
    resource_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerResourceEffects,
    ],
) -> list[SafetyPowerEndpoint]:
    """Order shutdowns so resources needed by pending endpoints remain available."""

    remaining = set(endpoints)
    ordered: list[SafetyPowerEndpoint] = []

    while remaining:
        ready = sorted(
            (
                endpoint
                for endpoint in remaining
                if not any(
                    resource
                    in requirements.get(
                        candidate,
                        SafetyPowerEndpointRequirements(
                            candidate,
                            frozenset(),
                        ),
                    ).required_resources
                    for resource in resource_effects.get(
                        endpoint,
                        SafetyPowerResourceEffects(
                            endpoint,
                            frozenset(),
                        ),
                    ).disabled_resources
                    for candidate in remaining
                    if candidate != endpoint
                )
            ),
            key=lambda endpoint: (
                endpoint.controller_id,
                endpoint.endpoint_id,
            ),
        )

        if not ready:
            raise SafetyPowerDependencyError(
                "no safe Safety Power shutdown order exists"
            )

        for endpoint in ready:
            ordered.append(endpoint)
            remaining.remove(endpoint)

    return ordered

def missing_required_shutdown_roles(
    topology: SafetyPowerTopology,
) -> frozenset[SafetyPowerRole]:
    """Return required Safety Power roles with no configured endpoint."""

    return frozenset(
        role
        for role in REQUIRED_SHUTDOWN_ROLES
        if topology.endpoint_for(role) is None
    )


def endpoints_missing_effects(
    topology: SafetyPowerTopology,
    endpoint_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointEffects,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return required shutdown endpoints with no configured effects."""

    required_endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SHUTDOWN_ROLES)
    )

    return frozenset(
        endpoint
        for endpoint in required_endpoints
        if endpoint not in endpoint_effects
    )


def roles_not_affected_by_mapped_endpoint(
    topology: SafetyPowerTopology,
    endpoint_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointEffects,
    ],
) -> frozenset[SafetyPowerRole]:
    """Return required roles not affected by their configured endpoint."""

    invalid_roles = set()

    for role in REQUIRED_SHUTDOWN_ROLES:
        endpoint = topology.endpoint_for(role)

        if endpoint is None:
            continue

        effects = endpoint_effects.get(endpoint)

        if effects is None:
            continue

        if not effects.affects(role):
            invalid_roles.add(role)

    return frozenset(invalid_roles)

def endpoints_missing_requirements(
    topology: SafetyPowerTopology,
    requirements: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointRequirements,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return required shutdown endpoints lacking explicit requirements."""

    endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SHUTDOWN_ROLES)
    )
    return frozenset(
        endpoint
        for endpoint in endpoints
        if endpoint not in requirements
    )


def endpoints_missing_resource_effects(
    topology: SafetyPowerTopology,
    resource_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerResourceEffects,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return required shutdown endpoints lacking explicit resource effects."""

    endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SHUTDOWN_ROLES)
    )
    return frozenset(
        endpoint
        for endpoint in endpoints
        if endpoint not in resource_effects
    )


def mismatched_endpoint_effects(
    endpoint_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointEffects,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return effect entries whose declared endpoint differs from their key."""

    return frozenset(
        endpoint
        for endpoint, effects in endpoint_effects.items()
        if effects.endpoint != endpoint
    )


def mismatched_endpoint_requirements(
    requirements: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointRequirements,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return requirement entries whose declared endpoint differs from key."""

    return frozenset(
        endpoint
        for endpoint, entry in requirements.items()
        if entry.endpoint != endpoint
    )


def mismatched_resource_effects(
    resource_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerResourceEffects,
    ],
) -> frozenset[SafetyPowerEndpoint]:
    """Return resource-effect entries whose declared endpoint differs from key."""

    return frozenset(
        endpoint
        for endpoint, entry in resource_effects.items()
        if entry.endpoint != endpoint
    )


@dataclass(frozen=True)
class SafetyPowerTopologyValidation:
    missing_roles: frozenset[SafetyPowerRole]
    missing_effects: frozenset[SafetyPowerEndpoint]
    mismatched_effects: frozenset[SafetyPowerEndpoint]
    missing_requirements: frozenset[SafetyPowerEndpoint]
    missing_resource_effects: frozenset[SafetyPowerEndpoint]
    mismatched_requirements: frozenset[SafetyPowerEndpoint]
    mismatched_resource_effects: frozenset[SafetyPowerEndpoint]
    roles_not_affected: frozenset[SafetyPowerRole]
    guardian_host_unsafe: frozenset[SafetyPowerEndpoint]
    guardian_resource_unsafe: frozenset[SafetyPowerEndpoint]
    self_disabling_endpoints: frozenset[SafetyPowerEndpoint]
    dependency_error: str | None = None

    @property
    def valid(self) -> bool:
        return not (
            self.missing_roles
            or self.missing_effects
            or self.mismatched_effects
            or self.missing_requirements
            or self.missing_resource_effects
            or self.mismatched_requirements
            or self.mismatched_resource_effects
            or self.roles_not_affected
            or self.guardian_host_unsafe
            or self.guardian_resource_unsafe
            or self.self_disabling_endpoints
            or self.dependency_error
        )


def validate_safety_power_topology(
    topology: SafetyPowerTopology,
    endpoint_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointEffects,
    ],
    requirements: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerEndpointRequirements,
    ],
    resource_effects: Mapping[
        SafetyPowerEndpoint,
        SafetyPowerResourceEffects,
    ],
    guardian_resources: GuardianSafetyResources,
) -> SafetyPowerTopologyValidation:
    """Validate topology requirements needed for commissioning."""

    missing_roles = missing_required_shutdown_roles(topology)
    missing_effects = endpoints_missing_effects(
        topology,
        endpoint_effects,
    )
    mismatched_effects = mismatched_endpoint_effects(
        endpoint_effects,
    )
    missing_requirements = endpoints_missing_requirements(
        topology,
        requirements,
    )
    missing_resource_effects = endpoints_missing_resource_effects(
        topology,
        resource_effects,
    )
    mismatched_requirements = mismatched_endpoint_requirements(
        requirements,
    )
    mismatched_resource_effect_entries = mismatched_resource_effects(
        resource_effects,
    )
    roles_not_affected = roles_not_affected_by_mapped_endpoint(
        topology,
        endpoint_effects,
    )
    guardian_unsafe = guardian_host_unsafe_endpoints(
        topology,
        endpoint_effects,
    )
    guardian_resource_unsafe = endpoints_disabling_guardian_resources(
        topology,
        resource_effects,
        guardian_resources,
    )
    self_disabling = endpoints_disabling_own_requirements(
        topology,
        requirements,
        resource_effects,
    )

    dependency_error = None

    if not missing_roles:
        endpoints = topology.endpoints_for_roles(
            set(REQUIRED_SHUTDOWN_ROLES)
        )

        try:
            order_shutdown_endpoints_by_resources(
                endpoints,
                requirements,
                resource_effects,
            )
        except SafetyPowerDependencyError as exc:
            dependency_error = str(exc)

    return SafetyPowerTopologyValidation(
        missing_roles=missing_roles,
        missing_effects=missing_effects,
        mismatched_effects=mismatched_effects,
        missing_requirements=missing_requirements,
        missing_resource_effects=missing_resource_effects,
        mismatched_requirements=mismatched_requirements,
        mismatched_resource_effects=mismatched_resource_effect_entries,
        roles_not_affected=roles_not_affected,
        guardian_host_unsafe=guardian_unsafe,
        guardian_resource_unsafe=guardian_resource_unsafe,
        self_disabling_endpoints=self_disabling,
        dependency_error=dependency_error,
    )

