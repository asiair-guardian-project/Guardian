"""Guardian 1.0 Safety Power capability probing."""

from collections.abc import Mapping

from modules.capability_probe import CapabilityProbeResult
from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    SafetyPowerRole,
)
from modules.safety_power import SafetyPowerTopology
from modules.safety_power_adapter import SafetyPowerAdapter


REQUIRED_SAFETY_POWER_ROLES = frozenset(
    {
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
    }
)


def probe_safety_power_control(
    *,
    topology: SafetyPowerTopology,
    adapters: Mapping[str, SafetyPowerAdapter],
) -> CapabilityProbeResult[bool]:
    """
    Non-destructively probe required Safety Power control paths.

    This function never switches an endpoint.
    """

    for role in REQUIRED_SAFETY_POWER_ROLES:
        if topology.endpoint_for(role) is None:
            return CapabilityProbeResult(
                capability=Capability.SAFETY_POWER_CONTROL,
                status=CapabilityStatus.FAILED,
                observation=False,
                detail=f"missing Safety Power endpoint for {role.name}",
            )

    endpoints = topology.endpoints_for_roles(
        set(REQUIRED_SAFETY_POWER_ROLES)
    )

    checked_in_batch = {}
    by_controller = {}

    for endpoint in endpoints:
        by_controller.setdefault(endpoint.controller_id, []).append(endpoint)

    for controller_id, group in by_controller.items():
        adapter = adapters.get(controller_id)

        if (
            adapter is not None
            and adapter.controller_id == controller_id
            and hasattr(adapter, "check_endpoints")
            and getattr(adapter, "supports_batch", False)
        ):
            try:
                checked_in_batch.update(adapter.check_endpoints(group))
            except Exception as exc:
                return CapabilityProbeResult(
                    capability=Capability.SAFETY_POWER_CONTROL,
                    status=CapabilityStatus.UNKNOWN,
                    observation=None,
                    detail=str(exc),
                )

    for endpoint in endpoints:
        adapter = adapters.get(endpoint.controller_id)

        if adapter is None:
            return CapabilityProbeResult(
                capability=Capability.SAFETY_POWER_CONTROL,
                status=CapabilityStatus.FAILED,
                observation=False,
                detail=(
                    "no Safety Power adapter for controller "
                    f"{endpoint.controller_id!r}"
                ),
            )

        if adapter.controller_id != endpoint.controller_id:
            return CapabilityProbeResult(
                capability=Capability.SAFETY_POWER_CONTROL,
                status=CapabilityStatus.FAILED,
                observation=False,
                detail=(
                    "Safety Power adapter identity does not match "
                    f"controller {endpoint.controller_id!r}"
                ),
            )

        try:
            if endpoint in checked_in_batch:
                if not checked_in_batch[endpoint]:
                    # Unreadable or wrongly named: the same UNKNOWN the
                    # per-outlet check gave, never a silent pass.
                    raise RuntimeError(
                        "Safety Power endpoint unreadable or misnamed: "
                        f"{endpoint.controller_id}/{endpoint.endpoint_id}"
                    )
                valid = True
            else:
                valid = adapter.check_endpoint(endpoint)
        except Exception as exc:
            return CapabilityProbeResult(
                capability=Capability.SAFETY_POWER_CONTROL,
                status=CapabilityStatus.UNKNOWN,
                observation=None,
                detail=str(exc),
            )

        if not valid:
            return CapabilityProbeResult(
                capability=Capability.SAFETY_POWER_CONTROL,
                status=CapabilityStatus.FAILED,
                observation=False,
                detail=(
                    "Safety Power endpoint validation failed: "
                    f"{endpoint.controller_id}/{endpoint.endpoint_id}"
                ),
            )

    return CapabilityProbeResult(
        capability=Capability.SAFETY_POWER_CONTROL,
        status=CapabilityStatus.AVAILABLE,
        observation=True,
        detail="required Safety Power endpoints are available",
    )
