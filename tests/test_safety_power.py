import pytest

from modules.safety_power import SafetyPowerEndpoint


def test_endpoint_identifies_controller_and_endpoint():
    endpoint = SafetyPowerEndpoint(
        controller_id="power-controller-1",
        endpoint_id="outlet-2",
    )

    assert endpoint.controller_id == "power-controller-1"
    assert endpoint.endpoint_id == "outlet-2"


def test_endpoint_is_hashable_for_shared_mapping_deduplication():
    endpoint_a = SafetyPowerEndpoint("controller-1", "output-1")
    endpoint_b = SafetyPowerEndpoint("controller-1", "output-1")

    assert endpoint_a == endpoint_b
    assert len({endpoint_a, endpoint_b}) == 1


@pytest.mark.parametrize(
    ("controller_id", "endpoint_id"),
    [
        ("", "output-1"),
        ("   ", "output-1"),
        ("controller-1", ""),
        ("controller-1", "   "),
    ],
)
def test_endpoint_rejects_empty_identifiers(controller_id, endpoint_id):
    with pytest.raises(ValueError):
        SafetyPowerEndpoint(controller_id, endpoint_id)


from modules.guardian_types import SafetyPowerRole
from modules.safety_power import SafetyPowerTopology


def test_topology_maps_role_to_endpoint():
    asiair_endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair_endpoint,
        }
    )

    assert topology.endpoint_for(SafetyPowerRole.ASIAIR) == asiair_endpoint
    assert topology.endpoint_for(SafetyPowerRole.MOUNT) is None


def test_shared_endpoint_is_deduplicated():
    shared_endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared_endpoint,
            SafetyPowerRole.MOUNT: shared_endpoint,
        }
    )

    endpoints = topology.endpoints_for_roles(
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
        }
    )

    assert endpoints == frozenset({shared_endpoint})


from modules.safety_power import SafetyPowerEndpointEffects


def test_endpoint_effects_identify_affected_roles():
    endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    effects = SafetyPowerEndpointEffects(
        endpoint=endpoint,
        affected_roles=frozenset(
            {
                SafetyPowerRole.ASIAIR,
                SafetyPowerRole.MOUNT,
            }
        ),
    )

    assert effects.affects(SafetyPowerRole.ASIAIR)
    assert effects.affects(SafetyPowerRole.MOUNT)
    assert not effects.affects(SafetyPowerRole.GUARDIAN_HOST)


def test_endpoint_effects_detect_guardian_host_dependency():
    endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    effects = SafetyPowerEndpointEffects(
        endpoint=endpoint,
        affected_roles=frozenset(
            {
                SafetyPowerRole.ASIAIR,
                SafetyPowerRole.GUARDIAN_HOST,
            }
        ),
    )

    assert effects.affects_guardian_host


from modules.safety_power import guardian_host_unsafe_endpoints


def test_required_endpoint_that_powers_guardian_host_is_unsafe():
    endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: endpoint,
        }
    )

    effects = {
        endpoint: SafetyPowerEndpointEffects(
            endpoint=endpoint,
            affected_roles=frozenset(
                {
                    SafetyPowerRole.ASIAIR,
                    SafetyPowerRole.GUARDIAN_HOST,
                }
            ),
        )
    }

    assert guardian_host_unsafe_endpoints(topology, effects) == frozenset(
        {endpoint}
    )


def test_shared_asiair_mount_endpoint_is_safe_if_guardian_remains_powered():
    endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: endpoint,
            SafetyPowerRole.MOUNT: endpoint,
        }
    )

    effects = {
        endpoint: SafetyPowerEndpointEffects(
            endpoint=endpoint,
            affected_roles=frozenset(
                {
                    SafetyPowerRole.ASIAIR,
                    SafetyPowerRole.MOUNT,
                }
            ),
        )
    }

    assert guardian_host_unsafe_endpoints(topology, effects) == frozenset()


from modules.safety_power import missing_required_shutdown_roles


def test_required_shutdown_roles_are_complete():
    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR:
                SafetyPowerEndpoint("controller-1", "output-1"),
            SafetyPowerRole.MOUNT:
                SafetyPowerEndpoint("controller-1", "output-2"),
            SafetyPowerRole.ACCESSORIES:
                SafetyPowerEndpoint("controller-1", "output-3"),
        }
    )

    assert missing_required_shutdown_roles(topology) == frozenset()


def test_missing_required_shutdown_role_is_reported():
    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR:
                SafetyPowerEndpoint("controller-1", "output-1"),
        }
    )

    assert missing_required_shutdown_roles(topology) == frozenset(
        {SafetyPowerRole.MOUNT, SafetyPowerRole.ACCESSORIES}
    )


def test_shared_endpoint_satisfies_both_required_roles():
    shared = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
            SafetyPowerRole.ACCESSORIES: shared,
        }
    )

    assert missing_required_shutdown_roles(topology) == frozenset()


from modules.safety_power import endpoints_missing_effects


def test_all_required_endpoints_have_effects():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    assert endpoints_missing_effects(topology, effects) == frozenset()


def test_required_endpoint_missing_effects_is_reported():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        )
    }

    assert endpoints_missing_effects(topology, effects) == frozenset(
        {mount}
    )


def test_shared_required_endpoint_needs_only_one_effects_record():
    shared = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
        }
    )

    effects = {
        shared: SafetyPowerEndpointEffects(
            shared,
            frozenset(
                {
                    SafetyPowerRole.ASIAIR,
                    SafetyPowerRole.MOUNT,
                }
            ),
        )
    }

    assert endpoints_missing_effects(topology, effects) == frozenset()


from modules.safety_power import validate_safety_power_topology


def test_complete_safe_topology_validates():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    accessories = SafetyPowerEndpoint("controller-c", "output-3")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
            SafetyPowerRole.ACCESSORIES: accessories,
        }
    )

    effects = {
        accessories: SafetyPowerEndpointEffects(
            accessories, frozenset({SafetyPowerRole.ACCESSORIES})
        ),
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        accessories: SafetyPowerEndpointRequirements(
            accessories, frozenset()
        ),
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
    }

    resource_effects = {
        accessories: SafetyPowerResourceEffects(
            accessories, frozenset()
        ),
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert result.valid


def test_validation_reports_missing_required_role():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {SafetyPowerRole.ASIAIR: asiair}
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        )
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        {},
        {},
        GuardianSafetyResources(frozenset()),
)

    assert not result.valid
    assert result.missing_roles == frozenset(
        {SafetyPowerRole.MOUNT, SafetyPowerRole.ACCESSORIES}
    )


def test_validation_reports_guardian_host_unsafe_endpoint():
    shared = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
        }
    )

    effects = {
        shared: SafetyPowerEndpointEffects(
            shared,
            frozenset(
                {
                    SafetyPowerRole.ASIAIR,
                    SafetyPowerRole.MOUNT,
                    SafetyPowerRole.GUARDIAN_HOST,
                }
            ),
        )
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        {},
        {},
        GuardianSafetyResources(frozenset()),
)

    assert not result.valid
    assert result.guardian_host_unsafe == frozenset({shared})


def test_validation_reports_circular_dependency():
    asiair = SafetyPowerEndpoint("controller-a", "output-1")
    mount = SafetyPowerEndpoint("controller-b", "output-1")

    accessories = SafetyPowerEndpoint("controller-c", "output-3")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
            SafetyPowerRole.ACCESSORIES: accessories,
        }
    )

    effects = {
        accessories: SafetyPowerEndpointEffects(
            accessories, frozenset({SafetyPowerRole.ACCESSORIES})
        ),
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    controller_a = SafetyPowerResource(
        "controller",
        "controller-a",
    )
    controller_b = SafetyPowerResource(
        "controller",
        "controller-b",
    )

    requirements = {
        accessories: SafetyPowerEndpointRequirements(
            accessories, frozenset()
        ),
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset({controller_a}),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset({controller_b}),
        ),
    }

    resource_effects = {
        accessories: SafetyPowerResourceEffects(
            accessories, frozenset()
        ),
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset({controller_b}),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset({controller_a}),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert not result.valid
    assert result.dependency_error is not None


from modules.safety_power import roles_not_affected_by_mapped_endpoint


def test_mapped_endpoint_must_affect_required_role():
    endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: endpoint,
        }
    )

    effects = {
        endpoint: SafetyPowerEndpointEffects(
            endpoint,
            frozenset({SafetyPowerRole.MOUNT}),
        )
    }

    assert roles_not_affected_by_mapped_endpoint(
        topology,
        effects,
    ) == frozenset({SafetyPowerRole.ASIAIR})


def test_correct_role_effect_is_accepted():
    endpoint = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: endpoint,
        }
    )

    effects = {
        endpoint: SafetyPowerEndpointEffects(
            endpoint,
            frozenset({SafetyPowerRole.ASIAIR}),
        )
    }

    assert roles_not_affected_by_mapped_endpoint(
        topology,
        effects,
    ) == frozenset()


def test_shared_endpoint_can_satisfy_both_required_roles():
    shared = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
        }
    )

    effects = {
        shared: SafetyPowerEndpointEffects(
            shared,
            frozenset(
                {
                    SafetyPowerRole.ASIAIR,
                    SafetyPowerRole.MOUNT,
                }
            ),
        )
    }

    assert roles_not_affected_by_mapped_endpoint(
        topology,
        effects,
    ) == frozenset()


def test_validation_rejects_role_not_affected_by_mapped_endpoint():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        {},
        {},
        GuardianSafetyResources(frozenset()),
)

    assert not result.valid
    assert result.roles_not_affected == frozenset(
        {SafetyPowerRole.ASIAIR}
    )

def test_required_roles_resolve_to_separate_endpoints():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    endpoints = topology.endpoints_for_roles(
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
        }
    )

    assert endpoints == frozenset({asiair, mount})


def test_required_roles_sharing_endpoint_are_deduplicated():
    shared = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
        }
    )

    endpoints = topology.endpoints_for_roles(
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
        }
    )

    assert endpoints == frozenset({shared})


from modules.safety_power import mismatched_endpoint_effects


def test_mismatched_endpoint_effects_detected():
    endpoint_a = SafetyPowerEndpoint("controller-1", "output-1")
    endpoint_b = SafetyPowerEndpoint("controller-1", "output-2")

    effects = {
        endpoint_a: SafetyPowerEndpointEffects(
            endpoint_b,
            frozenset({SafetyPowerRole.ASIAIR}),
        )
    }

    assert mismatched_endpoint_effects(effects) == frozenset(
        {endpoint_a}
    )



def test_validation_rejects_mismatched_endpoint_effects():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    wrong = SafetyPowerEndpoint("controller-1", "output-99")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            wrong,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        {},
        {},
        GuardianSafetyResources(frozenset()),
)

    assert not result.valid
    assert result.mismatched_effects == frozenset({asiair})


from modules.safety_power import (
    SafetyPowerDependencyError,
    GuardianSafetyResources,
    SafetyPowerEndpointRequirements,
    SafetyPowerResource,
    SafetyPowerResourceEffects,
)


def test_safety_power_resource_identifies_kind_and_resource():
    resource = SafetyPowerResource("controller", "pegasus")

    assert resource.kind == "controller"
    assert resource.resource_id == "pegasus"


@pytest.mark.parametrize(
    ("kind", "resource_id"),
    [
        ("", "pegasus"),
        ("   ", "pegasus"),
        ("controller", ""),
        ("controller", "   "),
    ],
)
def test_safety_power_resource_rejects_empty_identifiers(kind, resource_id):
    with pytest.raises(ValueError):
        SafetyPowerResource(kind, resource_id)


def test_endpoint_requirements_and_resource_effects_are_distinct():
    endpoint = SafetyPowerEndpoint("pegasus", "output-2")
    controller = SafetyPowerResource("controller", "pegasus")
    network = SafetyPowerResource("network", "observatory-lan")

    requirements = SafetyPowerEndpointRequirements(
        endpoint,
        frozenset({controller, network}),
    )
    effects = SafetyPowerResourceEffects(
        endpoint,
        frozenset({network}),
    )

    assert requirements.required_resources == frozenset(
        {controller, network}
    )
    assert effects.disabled_resources == frozenset({network})


from modules.safety_power import order_shutdown_endpoints_by_resources


def test_resource_order_puts_downstream_before_upstream():
    upstream = SafetyPowerEndpoint("pdu", "outlet-1")
    downstream = SafetyPowerEndpoint("pegasus", "output-2")
    pegasus = SafetyPowerResource("controller", "pegasus")

    requirements = {
        downstream: SafetyPowerEndpointRequirements(
            downstream,
            frozenset({pegasus}),
        )
    }
    effects = {
        upstream: SafetyPowerResourceEffects(
            upstream,
            frozenset({pegasus}),
        )
    }

    assert order_shutdown_endpoints_by_resources(
        {upstream, downstream},
        requirements,
        effects,
    ) == [downstream, upstream]


def test_resource_order_is_deterministic_without_dependencies():
    endpoint_b = SafetyPowerEndpoint("controller-b", "output-1")
    endpoint_a = SafetyPowerEndpoint("controller-a", "output-1")

    assert order_shutdown_endpoints_by_resources(
        {endpoint_b, endpoint_a},
        {},
        {},
    ) == [endpoint_a, endpoint_b]


def test_resource_order_rejects_circular_dependency():
    endpoint_a = SafetyPowerEndpoint("controller-a", "output-1")
    endpoint_b = SafetyPowerEndpoint("controller-b", "output-1")

    resource_a = SafetyPowerResource("controller", "controller-a")
    resource_b = SafetyPowerResource("controller", "controller-b")

    requirements = {
        endpoint_a: SafetyPowerEndpointRequirements(
            endpoint_a,
            frozenset({resource_a}),
        ),
        endpoint_b: SafetyPowerEndpointRequirements(
            endpoint_b,
            frozenset({resource_b}),
        ),
    }
    effects = {
        endpoint_a: SafetyPowerResourceEffects(
            endpoint_a,
            frozenset({resource_b}),
        ),
        endpoint_b: SafetyPowerResourceEffects(
            endpoint_b,
            frozenset({resource_a}),
        ),
    }

    with pytest.raises(SafetyPowerDependencyError):
        order_shutdown_endpoints_by_resources(
            {endpoint_a, endpoint_b},
            requirements,
            effects,
        )


def test_resource_order_preserves_network_path_needed_by_pending_endpoint():
    network_power = SafetyPowerEndpoint("pdu", "network-outlet")
    asiair_power = SafetyPowerEndpoint("controller-a", "asiair-outlet")

    observatory_lan = SafetyPowerResource(
        "network",
        "observatory-lan",
    )

    requirements = {
        asiair_power: SafetyPowerEndpointRequirements(
            asiair_power,
            frozenset({observatory_lan}),
        )
    }
    effects = {
        network_power: SafetyPowerResourceEffects(
            network_power,
            frozenset({observatory_lan}),
        )
    }

    assert order_shutdown_endpoints_by_resources(
        {network_power, asiair_power},
        requirements,
        effects,
    ) == [asiair_power, network_power]


def test_resource_order_preserves_guardian_host_until_required_actions_complete():
    host_power = SafetyPowerEndpoint("pdu", "guardian-host")
    mount_power = SafetyPowerEndpoint("controller-a", "mount-outlet")

    guardian_host = SafetyPowerResource(
        "host",
        "guardian",
    )

    requirements = {
        mount_power: SafetyPowerEndpointRequirements(
            mount_power,
            frozenset({guardian_host}),
        )
    }
    effects = {
        host_power: SafetyPowerResourceEffects(
            host_power,
            frozenset({guardian_host}),
        )
    }

    assert order_shutdown_endpoints_by_resources(
        {host_power, mount_power},
        requirements,
        effects,
    ) == [mount_power, host_power]


def test_validation_rejects_missing_required_endpoint_requirements():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset(),
        ),
    }

    resource_effects = {
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert result.missing_requirements == frozenset({mount})
    assert not result.valid


def test_validation_rejects_missing_required_resource_effects():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
    }

    resource_effects = {
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset(),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert result.missing_resource_effects == frozenset({mount})
    assert not result.valid


def test_validation_rejects_mismatched_requirement_endpoint():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        asiair: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
    }

    resource_effects = {
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert result.mismatched_requirements == frozenset({asiair})
    assert not result.valid


def test_validation_rejects_mismatched_resource_effect_endpoint():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
    }

    resource_effects = {
        asiair: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert result.mismatched_resource_effects == frozenset({asiair})
    assert not result.valid


def test_validation_rejects_endpoint_disabling_own_required_resource():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    network = SafetyPowerResource(
        "network",
        "observatory-lan",
    )

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset({network}),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
    }

    resource_effects = {
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset({network}),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
    }

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        GuardianSafetyResources(frozenset()),
)

    assert result.self_disabling_endpoints == frozenset({asiair})
    assert not result.valid


def test_validation_rejects_endpoint_disabling_guardian_required_resource():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-1", "output-2")

    guardian_network = SafetyPowerResource(
        "network",
        "observatory-lan",
    )

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    effects = {
        asiair: SafetyPowerEndpointEffects(
            asiair,
            frozenset({SafetyPowerRole.ASIAIR}),
        ),
        mount: SafetyPowerEndpointEffects(
            mount,
            frozenset({SafetyPowerRole.MOUNT}),
        ),
    }

    requirements = {
        asiair: SafetyPowerEndpointRequirements(
            asiair,
            frozenset(),
        ),
        mount: SafetyPowerEndpointRequirements(
            mount,
            frozenset(),
        ),
    }

    resource_effects = {
        asiair: SafetyPowerResourceEffects(
            asiair,
            frozenset({guardian_network}),
        ),
        mount: SafetyPowerResourceEffects(
            mount,
            frozenset(),
        ),
    }

    guardian_resources = GuardianSafetyResources(
        frozenset({guardian_network})
    )

    result = validate_safety_power_topology(
        topology,
        effects,
        requirements,
        resource_effects,
        guardian_resources,
    )

    assert result.guardian_resource_unsafe == frozenset({asiair})
    assert not result.valid
