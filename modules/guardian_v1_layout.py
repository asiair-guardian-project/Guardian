"""One place that says which outlets Guardian protects, cuts and may test, for the commissioning tools.

No `power` section in the installation config -> the fixed Starfront wiring (unchanged). With one, the operator's own
mapping (see guardian_v1_power_mapping). Read-only: this module never talks to a power controller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from modules.guardian_types import SafetyPowerRole
from modules.guardian_v1_mapped_kasa import ENDPOINT_IDS
from modules.guardian_v1_power_mapping import (
    REQUIRED_TARGETS, SUPPORTED_TYPES, PowerMapping, power_mapping_from_installation,
)
from modules.guardian_v1_starfront_kasa import CONTROLLER_ID as STARFRONT_CONTROLLER_ID, TARGETS as STARFRONT_TARGETS

STARFRONT_HOST = (1, "Mac Mini")
STARFRONT_TEST_OUTLETS = (5,)
STARFRONT_OUTLET_COUNT = 6


@dataclass(frozen=True)
class Target:
    role: SafetyPowerRole
    endpoint: str
    number: int
    alias: str


@dataclass(frozen=True)
class Layout:
    controller_type: str                      # "kasa_hs300" or "digital_loggers_rest"
    controller_id: str
    outlet_count: int
    host: Tuple[int, str]
    targets: Tuple[Target, ...]               # in shutdown order
    test_outlets: Optional[Tuple[int, ...]]   # None: any outlet nothing is mapped to
    starfront: bool
    options: Optional[dict] = None
    mapping: Optional[PowerMapping] = None    # the operator's mapping; None for the Starfront wiring

    @property
    def protected_numbers(self):
        return frozenset({self.host[0]} | {t.number for t in self.targets})

    @property
    def protected_aliases(self):
        return frozenset({self.host[1]} | {t.alias for t in self.targets})

    @property
    def confirm_token(self):
        """What the operator must type before a real rehearsal cut, e.g. CUT_OUTLETS_2_3_4."""
        return "CUT_OUTLETS_" + "_".join(str(n) for n in sorted(t.number for t in self.targets))

    def allowed_test_outlets(self):
        if self.test_outlets is not None:
            return tuple(self.test_outlets)
        return tuple(n for n in range(1, self.outlet_count + 1) if n not in self.protected_numbers)


def starfront_layout() -> Layout:
    targets = tuple(Target(role, endpoint, number, alias) for role, (endpoint, number, alias) in STARFRONT_TARGETS.items())
    return Layout("kasa_hs300", STARFRONT_CONTROLLER_ID, STARFRONT_OUTLET_COUNT, STARFRONT_HOST, targets,
                  STARFRONT_TEST_OUTLETS, True)


def layout_from_mapping(mapping: PowerMapping) -> Layout:
    targets = tuple(
        Target(role, ENDPOINT_IDS[name], mapping.targets[name].number, mapping.targets[name].alias)
        for name, role in sorted(REQUIRED_TARGETS.items(), key=lambda item: ENDPOINT_IDS[item[0]]))
    return Layout(mapping.controller_type, "configured_" + mapping.controller_type,
                  SUPPORTED_TYPES[mapping.controller_type],
                  (mapping.host_outlet.number, mapping.host_outlet.alias), targets, None, False,
                  dict(mapping.options or {}), mapping)


def layout_from_installation(installation) -> Layout:
    mapping = power_mapping_from_installation(installation or {})
    return starfront_layout() if mapping is None else layout_from_mapping(mapping)
