"""Starfront HS300 wiring for Guardian 1.0.

This module constructs the existing Kasa safety-power adapter and routing
callback. It does not enable hardware execution or ARM Guardian.
"""
from dataclasses import dataclass

from modules.guardian_types import SafetyPowerRole
from modules.kasa_controller import KasaController
from modules.kasa_safety_power_adapter import (
    KasaEndpointConfig, KasaSafetyPowerAdapter, PythonKasaTransport,
)
from modules.safety_power import (
    SafetyPowerEndpoint, SafetyPowerEndpointRequirements,
    SafetyPowerResourceEffects, SafetyPowerTopology,
)
from modules.safety_power_manager import SafetyPowerManager

CONTROLLER_ID = "starfront_hs300"
TARGETS = {
    SafetyPowerRole.ASIAIR: ("asiair", 2, "ASIAIR"),
    SafetyPowerRole.MOUNT: ("mount", 3, "Wave 150i"),
    SafetyPowerRole.ACCESSORIES: ("pegasus", 4, "Pegasus"),
}


@dataclass(frozen=True)
class StarfrontKasaWiring:
    topology: SafetyPowerTopology
    adapters: dict
    execute_safety_power: object


def compose_starfront_kasa(*, host: str, transport=None) -> StarfrontKasaWiring:
    """Wire exactly three verified shutdown targets; never outlet 1.

    Passing a fake transport enables completely hardware-free tests.
    With no transport, credentials come from Guardian's existing Keychain
    retrieval path; construction itself sends no Kasa commands.
    """
    if transport is None:
        username, password = KasaController(host)._credentials()
        transport = PythonKasaTransport(
            host=host, username=username, password=password
        )

    endpoint_configs = {
        endpoint_id: KasaEndpointConfig(number, alias)
        for endpoint_id, number, alias in TARGETS.values()
    }
    adapter = KasaSafetyPowerAdapter(
        controller_id=CONTROLLER_ID,
        endpoints=endpoint_configs,
        transport=transport,
    )
    topology = SafetyPowerTopology({
        role: SafetyPowerEndpoint(CONTROLLER_ID, endpoint_id)
        for role, (endpoint_id, _, _) in TARGETS.items()
    })
    manager = SafetyPowerManager({CONTROLLER_ID: adapter})
    endpoints = set(topology.endpoints_for_roles(set(TARGETS)))
    requirements = {
        ep: SafetyPowerEndpointRequirements(ep, frozenset())
        for ep in endpoints
    }
    effects = {
        ep: SafetyPowerResourceEffects(ep, frozenset())
        for ep in endpoints
    }

    def execute_safety_power(roles):
        return manager.power_off_roles(
            set(roles), topology, requirements, effects
        )

    return StarfrontKasaWiring(
        topology=topology,
        adapters={CONTROLLER_ID: adapter},
        execute_safety_power=execute_safety_power,
    )
