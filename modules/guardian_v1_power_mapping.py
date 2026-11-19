"""Which outlet powers what: the optional `power` section of the installation configuration.

    power:
      type: kasa_hs300                                  # or digital_loggers_rest (8 outlets; optional scheme, port)
      host_outlet: {number: 1, alias: "Mac Mini"}      # the computer running Guardian. NEVER switched.
      targets:                                          # what Guardian cuts when it must protect the rig
        asiair:      {number: 2, alias: "ASIAIR"}
        mount:       {number: 3, alias: "Wave 150i"}
        accessories: {number: 4, alias: "Pegasus"}

The alias is the name shown in the Kasa app. Before every power-off the strip's own name for that outlet must match it,
so a renamed or re-plugged outlet is refused, never cut by number alone.

Without a `power` section Guardian uses its fixed Starfront layout (see guardian_v1_starfront_kasa), exactly as before.
This module only reads and validates; it never contacts hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from modules.guardian_types import SafetyPowerRole

SUPPORTED_TYPES = {"kasa_hs300": 6, "digital_loggers_rest": 8}   # controller type -> number of outlets
DLI_OPTIONS = {"scheme", "port"}             # optional extras, Digital Loggers only
REQUIRED_TARGETS = {                          # config name -> role (all three, one outlet each)
    "asiair": SafetyPowerRole.ASIAIR,
    "mount": SafetyPowerRole.MOUNT,
    "accessories": SafetyPowerRole.ACCESSORIES,
}
MAX_ALIAS_LENGTH = 64


class PowerMappingError(ValueError):
    pass


@dataclass(frozen=True)
class Outlet:
    number: int
    alias: str


@dataclass(frozen=True)
class PowerMapping:
    controller_type: str
    host_outlet: Outlet
    targets: Mapping[str, Outlet]        # keyed by REQUIRED_TARGETS names
    options: Mapping[str, Any] = None    # Digital Loggers only: scheme ("http"/"https"), port

    def target_for_role(self, role: SafetyPowerRole) -> Outlet:
        for name, wanted in REQUIRED_TARGETS.items():
            if wanted is role:
                return self.targets[name]
        raise KeyError(role)


def _outlet(value: Any, field: str, outlet_count: int) -> Outlet:
    if not isinstance(value, Mapping) or set(value) != {"number", "alias"}:
        raise PowerMappingError(f"{field}: expected exactly a number and an alias")
    number, alias = value["number"], value["alias"]
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= outlet_count:
        raise PowerMappingError(f"{field}: the outlet number must be a whole number from 1 to {outlet_count}")
    if not isinstance(alias, str) or not alias.strip() or alias != alias.strip():
        raise PowerMappingError(f"{field}: the outlet name must be text with no leading or trailing spaces")
    if len(alias) > MAX_ALIAS_LENGTH or any(ord(ch) < 32 for ch in alias):
        raise PowerMappingError(f"{field}: the outlet name is too long or has control characters")
    return Outlet(number, alias)


def parse_power_section(section: Any) -> PowerMapping:
    """Validate a `power` section. Raises PowerMappingError with a plain reason; never touches hardware."""
    if not isinstance(section, Mapping):
        raise PowerMappingError("power: expected a section with type, host_outlet and targets")
    allowed = {"type", "host_outlet", "targets"}
    if section.get("type") == "digital_loggers_rest":
        allowed |= DLI_OPTIONS
    unknown = set(section) - allowed
    if unknown:
        raise PowerMappingError("power: unknown setting " + ", ".join(sorted(map(str, unknown))))
    controller_type = section.get("type")
    if controller_type not in SUPPORTED_TYPES:
        raise PowerMappingError(f"power.type: supported types are {', '.join(sorted(SUPPORTED_TYPES))}")
    count = SUPPORTED_TYPES[controller_type]
    if "host_outlet" not in section:
        raise PowerMappingError("power.host_outlet: say which outlet powers the computer running Guardian")
    host = _outlet(section["host_outlet"], "power.host_outlet", count)
    targets = section.get("targets")
    if not isinstance(targets, Mapping) or set(targets) != set(REQUIRED_TARGETS):
        raise PowerMappingError("power.targets: exactly " + ", ".join(REQUIRED_TARGETS) + " are required")
    parsed = {name: _outlet(targets[name], f"power.targets.{name}", count) for name in REQUIRED_TARGETS}

    everything = [("host_outlet", host)] + list(parsed.items())
    numbers = [outlet.number for _, outlet in everything]
    if len(set(numbers)) != len(numbers):
        raise PowerMappingError("power: two entries use the same outlet number")
    aliases = [outlet.alias.casefold() for _, outlet in everything]
    if len(set(aliases)) != len(aliases):
        raise PowerMappingError("power: two entries use the same outlet name")
    options = {}
    if controller_type == "digital_loggers_rest":
        scheme = section.get("scheme", "http")
        if scheme not in ("http", "https"):
            raise PowerMappingError("power.scheme: must be http or https")
        options["scheme"] = scheme
        if "port" in section:
            port = section["port"]
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise PowerMappingError("power.port: must be a whole number from 1 to 65535")
            options["port"] = port
    return PowerMapping(controller_type, host, parsed, options)


def power_mapping_from_installation(installation: Mapping[str, Any]) -> PowerMapping | None:
    """None means no `power` section: the fixed Starfront layout applies."""
    if "power" not in installation:
        return None
    return parse_power_section(installation["power"])
