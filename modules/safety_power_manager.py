"""Guardian 1.0 Safety Power adapter routing."""

from collections.abc import Mapping
from dataclasses import dataclass

from modules.guardian_types import SafetyPowerResult, SafetyPowerRole
from modules.safety_power import (
    SafetyPowerEndpoint,
    SafetyPowerEndpointRequirements,
    SafetyPowerResourceEffects,
    SafetyPowerTopology,
    order_shutdown_endpoints_by_resources,
)
from modules.safety_power_adapter import SafetyPowerAdapter


@dataclass(frozen=True)
class SafetyPowerEndpointRecord:
    endpoint: SafetyPowerEndpoint
    result: SafetyPowerResult


@dataclass(frozen=True)
class SafetyPowerRoleRecord:
    role: SafetyPowerRole
    endpoint: SafetyPowerEndpoint | None
    result: SafetyPowerResult


class SafetyPowerRoutingError(ValueError):
    """Raised when an endpoint cannot be safely routed to a controller."""


class SafetyPowerManager:
    """Routes Safety Power Endpoints to their configured controller adapters."""

    def __init__(
        self,
        adapters: Mapping[str, SafetyPowerAdapter],
    ) -> None:
        self._adapters = dict(adapters)

    def adapter_for(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerAdapter:
        adapter = self._adapters.get(endpoint.controller_id)

        if adapter is None:
            raise SafetyPowerRoutingError(
                f"no Safety Power adapter for controller "
                f"{endpoint.controller_id!r}"
            )

        if adapter.controller_id != endpoint.controller_id:
            raise SafetyPowerRoutingError(
                f"adapter controller ID {adapter.controller_id!r} "
                f"does not match endpoint controller ID "
                f"{endpoint.controller_id!r}"
            )

        return adapter

    def power_off(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerResult:
        """Command one endpoint OFF and verify where supported."""

        adapter = self.adapter_for(endpoint)

        command_result = adapter.power_off(endpoint)

        if command_result is SafetyPowerResult.FAILED:
            return SafetyPowerResult.FAILED

        if not adapter.supports_verification:
            return SafetyPowerResult.COMMANDED_UNVERIFIED

        try:
            verification_result = adapter.verify_off(endpoint)
        except Exception:
            return SafetyPowerResult.FAILED

        if verification_result is SafetyPowerResult.VERIFIED_OFF:
            return SafetyPowerResult.VERIFIED_OFF

        return SafetyPowerResult.FAILED

    def power_off_endpoints(
        self,
        endpoints: set[SafetyPowerEndpoint],
        requirements: Mapping[
            SafetyPowerEndpoint,
            SafetyPowerEndpointRequirements,
        ],
        resource_effects: Mapping[
            SafetyPowerEndpoint,
            SafetyPowerResourceEffects,
        ],
    ) -> list[SafetyPowerEndpointRecord]:
        """Power off endpoints in dependency-safe order."""

        ordered = order_shutdown_endpoints_by_resources(
            endpoints,
            requirements,
            resource_effects,
        )
        batch_results = self._power_off_batched(ordered)
        records = []

        for endpoint in ordered:
            if endpoint in batch_results:
                result = batch_results[endpoint]
            else:
                try:
                    result = self.power_off(endpoint)
                except Exception:
                    result = SafetyPowerResult.FAILED

            records.append(
                SafetyPowerEndpointRecord(
                    endpoint=endpoint,
                    result=result,
                )
            )

        return records

    def _power_off_batched(self, ordered):
        """Power off endpoints of batch-capable controllers over one session.

        Returns {endpoint: result} for endpoints it handled. Anything it
        does not handle (no batch support, no routing) falls back to the
        one-at-a-time path, so behaviour for other controllers is unchanged.
        Command order within a controller follows the shutdown ordering.
        """

        groups = {}

        for endpoint in ordered:
            try:
                adapter = self.adapter_for(endpoint)
            except SafetyPowerRoutingError:
                continue

            if (
                getattr(adapter, "supports_batch", False)
                and adapter.supports_verification
            ):
                groups.setdefault(endpoint.controller_id, []).append(endpoint)

        handled = {}

        for controller_id, group in groups.items():
            adapter = self._adapters[controller_id]

            try:
                commanded = adapter.power_off_many(group)
            except Exception:
                commanded = {}

            sent = [
                endpoint
                for endpoint in group
                if commanded.get(endpoint)
                is SafetyPowerResult.COMMANDED_UNVERIFIED
            ]
            verified = {}

            if sent:
                try:
                    verified = adapter.verify_off_many(sent)
                except Exception:
                    verified = {}

            for endpoint in group:
                if verified.get(endpoint) is SafetyPowerResult.VERIFIED_OFF:
                    handled[endpoint] = SafetyPowerResult.VERIFIED_OFF
                else:
                    handled[endpoint] = SafetyPowerResult.FAILED

        return handled

    def power_off_roles(
        self,
        roles: set[SafetyPowerRole],
        topology: SafetyPowerTopology,
        requirements: Mapping[
            SafetyPowerEndpoint,
            SafetyPowerEndpointRequirements,
        ],
        resource_effects: Mapping[
            SafetyPowerEndpoint,
            SafetyPowerResourceEffects,
        ],
    ) -> list[SafetyPowerRoleRecord]:
        """Power off logical roles through their mapped endpoints."""

        endpoints = topology.endpoints_for_roles(roles)

        endpoint_records = self.power_off_endpoints(
            set(endpoints),
            requirements,
            resource_effects,
        )

        results_by_endpoint = {
            record.endpoint: record.result
            for record in endpoint_records
        }

        role_records = []

        for role in sorted(roles, key=lambda item: item.value):
            endpoint = topology.endpoint_for(role)

            if endpoint is None:
                role_records.append(
                    SafetyPowerRoleRecord(
                        role=role,
                        endpoint=None,
                        result=SafetyPowerResult.FAILED,
                    )
                )
                continue

            role_records.append(
                SafetyPowerRoleRecord(
                    role=role,
                    endpoint=endpoint,
                    result=results_by_endpoint[endpoint],
                )
            )

        return role_records
