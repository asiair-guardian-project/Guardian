"""Kasa safety-power wiring built from the operator's `power` section (see guardian_v1_power_mapping).

A separate path beside guardian_v1_starfront_kasa, which is unchanged and still used whenever there is no `power`
section. Same adapter, same routing, same per-outlet name check before every power-off. Adds one more guard: the
transport handed to the adapter refuses to switch the host computer's outlet, whatever the mapping says.
Construction sends no Kasa commands.
"""
import logging
from dataclasses import dataclass

from modules.guardian_v1_power_mapping import REQUIRED_TARGETS, PowerMapping
from modules.kasa_controller import KasaController
from modules.kasa_safety_power_adapter import (
    KasaEndpointConfig, KasaSafetyPowerAdapter, PythonKasaTransport,
)
from modules.safety_power import (
    SafetyPowerEndpoint, SafetyPowerEndpointRequirements,
    SafetyPowerResourceEffects, SafetyPowerTopology,
)
from modules.safety_power_manager import SafetyPowerManager

_logger = logging.getLogger("guardian_v1.mapped_kasa")

# Shutdowns are ordered by endpoint name. The fixed Starfront wiring names them asiair, mount, pegasus, which sorts as
# ASIAIR, then mount, then accessories. These numbered names keep exactly that order for any outlet numbers.
ENDPOINT_IDS = {"asiair": "1_asiair", "mount": "2_mount", "accessories": "3_accessories"}


class HostOutletGuard:
    """Wraps a Kasa transport. Reading is untouched; switching the host computer's outlet is refused."""

    def __init__(self, transport, *, host_number, host_alias):
        self._transport = transport
        self._host_number = host_number
        self._host_alias = host_alias.casefold()

    def _is_host(self, outlet_number, expected_alias):
        return outlet_number == self._host_number or str(expected_alias).casefold() == self._host_alias

    def check_outlet(self, outlet_number, expected_alias):
        return self._transport.check_outlet(outlet_number, expected_alias)

    def get_outlet_state(self, outlet_number, expected_alias):
        return self._transport.get_outlet_state(outlet_number, expected_alias)

    def power_off_outlet(self, outlet_number, expected_alias):
        if self._is_host(outlet_number, expected_alias):
            _logger.critical("Refused to switch the host computer's outlet (%s)", outlet_number)
            return False
        return self._transport.power_off_outlet(outlet_number, expected_alias)

    def close(self):
        close = getattr(self._transport, "close", None)
        if close is not None:
            close()

    # The real transport also offers batch calls that use ONE connection (the strip dislikes closely spaced ones),
    # and the adapter uses them whenever they exist. Mirror them exactly when the wrapped transport has them, so the
    # connection behaviour matches the fixed Starfront wiring; hide them when it does not.
    def __getattr__(self, name):
        if name == "get_outlet_states" and hasattr(self._transport, name):
            return self._transport.get_outlet_states
        if name == "power_off_outlets" and hasattr(self._transport, name):
            return self._guarded_power_off_outlets
        raise AttributeError(name)

    def _guarded_power_off_outlets(self, requests):
        requests = list(requests)
        allowed = [(number, alias) for number, alias in requests if not self._is_host(number, alias)]
        refused = {number: False for number, alias in requests if self._is_host(number, alias)}
        for number in refused:
            _logger.critical("Refused to switch the host computer's outlet (%s)", number)
        result = dict(self._transport.power_off_outlets(allowed)) if allowed else {}
        result.update(refused)
        return result


@dataclass(frozen=True)
class MappedKasaWiring:
    topology: SafetyPowerTopology
    adapters: dict
    execute_safety_power: object


def compose_mapped_kasa(*, host: str, mapping: PowerMapping, transport=None) -> MappedKasaWiring:
    """Wire exactly the three mapped shutdown targets; never the host outlet.

    Passing a fake transport enables completely hardware-free tests. With no transport, credentials come from
    Guardian's existing Keychain retrieval path; construction itself sends no Kasa commands.
    """
    if transport is None and mapping.controller_type == "digital_loggers_rest":
        from modules.guardian_v1_dli_transport import DigitalLoggersTransport, dli_credentials
        username, password = dli_credentials()
        transport = DigitalLoggersTransport(
            host=host, username=username, password=password,
            port=(mapping.options or {}).get("port"), scheme=(mapping.options or {}).get("scheme", "http"))
    elif transport is None:
        username, password = KasaController(host)._credentials()
        transport = PythonKasaTransport(host=host, username=username, password=password)
    transport = HostOutletGuard(transport, host_number=mapping.host_outlet.number,
                                host_alias=mapping.host_outlet.alias)

    controller_id = "configured_" + mapping.controller_type
    endpoint_configs = {
        ENDPOINT_IDS[name]: KasaEndpointConfig(mapping.targets[name].number, mapping.targets[name].alias)
        for name in REQUIRED_TARGETS
    }
    adapter = KasaSafetyPowerAdapter(controller_id=controller_id, endpoints=endpoint_configs, transport=transport)
    topology = SafetyPowerTopology({
        role: SafetyPowerEndpoint(controller_id, ENDPOINT_IDS[name]) for name, role in REQUIRED_TARGETS.items()
    })
    manager = SafetyPowerManager({controller_id: adapter})
    endpoints = set(topology.endpoints_for_roles(set(REQUIRED_TARGETS.values())))
    requirements = {ep: SafetyPowerEndpointRequirements(ep, frozenset()) for ep in endpoints}
    effects = {ep: SafetyPowerResourceEffects(ep, frozenset()) for ep in endpoints}

    def execute_safety_power(roles):
        return manager.power_off_roles(set(roles), topology, requirements, effects)

    return MappedKasaWiring(topology=topology, adapters={controller_id: adapter},
                            execute_safety_power=execute_safety_power)
