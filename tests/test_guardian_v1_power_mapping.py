"""Operator-defined outlet mapping: validation, the host-outlet guard, equivalence with the fixed Starfront wiring,
and a full simulated night on a layout that is not Starfront's."""

import copy
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from modules.guardian_types import SafetyPowerRole as Role, SafetyPowerState, SessionState
from modules.guardian_v1_configuration_identity import semantic_fingerprint
from modules.guardian_v1_mapped_kasa import ENDPOINT_IDS, HostOutletGuard, compose_mapped_kasa
from modules.guardian_v1_power_mapping import (
    PowerMappingError, parse_power_section, power_mapping_from_installation,
)
from modules.guardian_v1_sim_night import INSTALLATION, SimRig, build_sim_monitor, prepare_folder
from modules.guardian_v1_starfront_kasa import compose_starfront_kasa

STARFRONT = {
    "type": "kasa_hs300",
    "host_outlet": {"number": 1, "alias": "Mac Mini"},
    "targets": {"asiair": {"number": 2, "alias": "ASIAIR"},
                "mount": {"number": 3, "alias": "Wave 150i"},
                "accessories": {"number": 4, "alias": "Pegasus"}},
}
OTHER = {   # a layout unlike Starfront's: different numbers, different names, host on outlet 6
    "type": "kasa_hs300",
    "host_outlet": {"number": 6, "alias": "Control Mac"},
    "targets": {"asiair": {"number": 1, "alias": "Air Plus"},
                "mount": {"number": 2, "alias": "AM5N"},
                "accessories": {"number": 3, "alias": "Dew Box"}},
}
OTHER_STRIP = {1: "Air Plus", 2: "AM5N", 3: "Dew Box", 4: "Spare A", 5: "Spare B", 6: "Control Mac"}
ALL_ROLES = {Role.ASIAIR, Role.MOUNT, Role.ACCESSORIES}


def changed(base, path, value):
    result = copy.deepcopy(base)
    node = result
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return result


# ---- validation ------------------------------------------------------------------------------

def test_a_good_section_parses():
    mapping = parse_power_section(OTHER)
    assert mapping.controller_type == "kasa_hs300"
    assert (mapping.host_outlet.number, mapping.host_outlet.alias) == (6, "Control Mac")
    assert mapping.target_for_role(Role.MOUNT).number == 2
    assert mapping.target_for_role(Role.ACCESSORIES).alias == "Dew Box"


@pytest.mark.parametrize("bad", [
    "not a mapping",
    {**STARFRONT, "extra": 1},
    {**STARFRONT, "type": "mystery_strip"},
    {k: v for k, v in STARFRONT.items() if k != "host_outlet"},
    {k: v for k, v in STARFRONT.items() if k != "targets"},
    changed(STARFRONT, ["targets", "spare"], {"number": 5, "alias": "Spare"}),
    {**STARFRONT, "targets": {k: v for k, v in STARFRONT["targets"].items() if k != "mount"}},
    changed(STARFRONT, ["targets", "asiair", "number"], 0),
    changed(STARFRONT, ["targets", "asiair", "number"], 7),
    changed(STARFRONT, ["targets", "asiair", "number"], True),
    changed(STARFRONT, ["targets", "asiair", "number"], "2"),
    changed(STARFRONT, ["targets", "asiair", "alias"], ""),
    changed(STARFRONT, ["targets", "asiair", "alias"], " ASIAIR"),
    changed(STARFRONT, ["targets", "asiair", "alias"], "A" * 65),
    changed(STARFRONT, ["targets", "asiair", "alias"], "bad\x00name"),
    changed(STARFRONT, ["targets", "asiair", "alias"], 5),
    changed(STARFRONT, ["host_outlet"], {"number": 1}),
    changed(STARFRONT, ["targets", "mount", "number"], 2),                 # same number as asiair
    changed(STARFRONT, ["targets", "mount", "number"], 1),                 # the host's outlet
    changed(STARFRONT, ["targets", "mount", "alias"], "asiair"),           # same name, other case
    changed(STARFRONT, ["targets", "mount", "alias"], "mac mini"),         # the host's name
])
def test_every_unsafe_or_malformed_section_is_refused(bad):
    with pytest.raises(PowerMappingError):
        parse_power_section(bad)


def test_no_power_section_means_the_fixed_starfront_layout():
    assert power_mapping_from_installation(INSTALLATION) is None
    assert power_mapping_from_installation({**INSTALLATION, "power": OTHER}).host_outlet.number == 6
    with pytest.raises(PowerMappingError):
        power_mapping_from_installation({**INSTALLATION, "power": {"type": "kasa_hs300"}})


def test_changing_the_mapping_changes_the_configuration_identity_so_commissioning_must_be_redone():
    base = semantic_fingerprint(INSTALLATION)
    assert semantic_fingerprint({**INSTALLATION, "power": STARFRONT}) != base
    assert semantic_fingerprint({**INSTALLATION, "power": OTHER}) != semantic_fingerprint({**INSTALLATION, "power": STARFRONT})
    assert semantic_fingerprint(INSTALLATION) == base                       # no section: identity untouched


# ---- fake strips -----------------------------------------------------------------------------

class Strip:
    """Single-outlet calls only (no batch methods)."""

    def __init__(self, names):
        self.names = dict(names)
        self.on = {n: True for n in names}
        self.log = []

    def check_outlet(self, number, alias):
        self.log.append(("check", number, alias))
        return self.names.get(number) == alias

    def get_outlet_state(self, number, alias):
        self.log.append(("state", number, alias))
        return SafetyPowerState.ON if self.on[number] else SafetyPowerState.OFF

    def power_off_outlet(self, number, alias):
        self.log.append(("off", number, alias))
        if self.names.get(number) != alias:
            return False
        self.on[number] = False
        return True


class BatchStrip(Strip):
    """Also has the batch calls the real transport has (one connection for several outlets)."""

    def get_outlet_states(self, requests):
        self.log.append(("states", tuple(requests)))
        return {n: (SafetyPowerState.ON if self.on[n] else SafetyPowerState.OFF) for n, _ in requests}

    def power_off_outlets(self, requests):
        self.log.append(("offs", tuple(requests)))
        out = {}
        for number, alias in requests:
            ok = self.names.get(number) == alias
            if ok:
                self.on[number] = False
            out[number] = ok
        return out


STARFRONT_STRIP = {1: "Mac Mini", 2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus", 5: "spare", 6: "Plug 6"}


# ---- the host-outlet guard -------------------------------------------------------------------

def test_the_guard_refuses_to_switch_the_host_outlet_by_number_or_by_name():
    strip = Strip(OTHER_STRIP)
    guard = HostOutletGuard(strip, host_number=6, host_alias="Control Mac")
    assert guard.power_off_outlet(6, "Control Mac") is False
    assert guard.power_off_outlet(6, "whatever") is False              # by number
    assert guard.power_off_outlet(2, "control mac") is False           # by name, any case
    assert [entry for entry in strip.log if entry[0] == "off"] == []
    assert strip.on[6] is True
    assert guard.power_off_outlet(1, "Air Plus") is True               # ordinary outlets pass through
    assert strip.on[1] is False


def test_the_guard_filters_the_host_out_of_batch_cuts_and_passes_the_rest():
    strip = BatchStrip(OTHER_STRIP)
    guard = HostOutletGuard(strip, host_number=6, host_alias="Control Mac")
    result = guard.power_off_outlets([(1, "Air Plus"), (6, "Control Mac"), (2, "AM5N")])
    assert result == {1: True, 2: True, 6: False}
    assert strip.log == [("offs", ((1, "Air Plus"), (2, "AM5N")))]
    assert strip.on[6] is True
    assert guard.power_off_outlets([(6, "Control Mac")]) == {6: False}
    assert [e for e in strip.log if e[0] == "offs"] == [("offs", ((1, "Air Plus"), (2, "AM5N")))]   # nothing sent


def test_the_guard_only_offers_batch_calls_the_wrapped_transport_has():
    plain = HostOutletGuard(Strip(OTHER_STRIP), host_number=6, host_alias="Control Mac")
    batch = HostOutletGuard(BatchStrip(OTHER_STRIP), host_number=6, host_alias="Control Mac")
    assert not hasattr(plain, "power_off_outlets") and not hasattr(plain, "get_outlet_states")
    assert hasattr(batch, "power_off_outlets") and hasattr(batch, "get_outlet_states")
    assert batch.get_outlet_states([(1, "Air Plus")]) == {1: SafetyPowerState.ON}


def test_the_guard_reads_through_and_closes_the_wrapped_transport():
    closed = []

    class Closable(Strip):
        def close(self):
            closed.append(True)
    guard = HostOutletGuard(Closable(OTHER_STRIP), host_number=6, host_alias="Control Mac")
    assert guard.check_outlet(1, "Air Plus") is True and guard.check_outlet(1, "wrong") is False
    assert guard.get_outlet_state(2, "AM5N") is SafetyPowerState.ON
    guard.close()
    assert closed == [True]


# ---- equivalence with the fixed Starfront wiring ---------------------------------------------

@pytest.mark.parametrize("make", [Strip, BatchStrip])
@pytest.mark.parametrize("roles", [ALL_ROLES, {Role.ASIAIR}, {Role.MOUNT, Role.ACCESSORIES}])
def test_the_mapped_wiring_behaves_exactly_like_the_starfront_wiring_for_the_same_layout(make, roles):
    fixed, mapped = make(STARFRONT_STRIP), make(STARFRONT_STRIP)
    fixed_result = compose_starfront_kasa(host="h", transport=fixed).execute_safety_power(roles)
    mapped_result = compose_mapped_kasa(host="h", mapping=parse_power_section(STARFRONT),
                                        transport=mapped).execute_safety_power(roles)
    assert mapped.log == fixed.log                                   # same commands, same order, same connections
    assert [(r.role, r.result) for r in mapped_result] == [(r.role, r.result) for r in fixed_result]
    assert mapped.on == fixed.on and mapped.on[1] is True            # the Mac Mini outlet untouched


def test_shutdown_order_is_asiair_then_mount_then_accessories_for_any_outlet_numbers():
    strip = Strip(OTHER_STRIP)
    compose_mapped_kasa(host="h", mapping=parse_power_section(OTHER), transport=strip).execute_safety_power(ALL_ROLES)
    assert [(n, a) for kind, n, a in strip.log if kind == "off"] == [(1, "Air Plus"), (2, "AM5N"), (3, "Dew Box")]
    assert sorted(ENDPOINT_IDS.values()) == [ENDPOINT_IDS["asiair"], ENDPOINT_IDS["mount"], ENDPOINT_IDS["accessories"]]


def test_a_mapped_layout_cuts_only_its_targets_and_never_the_host_or_spares():
    for make in (Strip, BatchStrip):
        strip = make(OTHER_STRIP)
        compose_mapped_kasa(host="h", mapping=parse_power_section(OTHER), transport=strip).execute_safety_power(ALL_ROLES)
        assert strip.on == {1: False, 2: False, 3: False, 4: True, 5: True, 6: True}


def test_a_renamed_outlet_is_refused_not_cut_by_number():
    renamed = {**OTHER_STRIP, 2: "Something else"}
    strip = BatchStrip(renamed)
    result = compose_mapped_kasa(host="h", mapping=parse_power_section(OTHER),
                                 transport=strip).execute_safety_power(ALL_ROLES)
    assert strip.on[2] is True                                        # the mount outlet was not switched
    by_role = {r.role: r.result for r in result}
    assert by_role[Role.MOUNT].name != "VERIFIED_OFF"


# ---- composing, and the monitor's startup ----------------------------------------------------

def test_the_integration_uses_the_fixed_layout_without_a_mapping_and_the_mapped_one_with_it(monkeypatch):
    import modules.guardian_v1_starfront_kasa_integration as integration
    used = []
    monkeypatch.setattr(integration, "compose_starfront_kasa", lambda **kw: used.append("fixed") or (_ for _ in ()).throw(StopIteration()))
    monkeypatch.setattr(integration, "compose_mapped_kasa", lambda **kw: used.append("mapped") or (_ for _ in ()).throw(StopIteration()))
    base = dict(application=type("A", (), {"mode": type("M", (), {"hardware_execution_enabled": False})(),
                                           "recovery_store": object()})(),
                asiair_host="192.0.2.10", alpaca_host="h.example", alpaca_port=443, alpaca_device_number=1,
                kasa_host="192.0.2.20")
    for mapping in (None, parse_power_section(OTHER)):
        with pytest.raises(StopIteration):
            integration.compose_starfront_kasa_integration(power_mapping=mapping, **base)
    assert used == ["fixed", "mapped"]


def installation_with(power):
    return {**copy.deepcopy(INSTALLATION), "power": power}


def test_an_invalid_power_section_stops_the_monitor_from_starting(tmp_path):
    bad = installation_with({"type": "kasa_hs300"})
    folder = prepare_folder(None, installation=bad)
    with pytest.raises(SystemExit) as exit_info:
        build_sim_monitor(folder, SimRig(folder, say=lambda t: None, outlet_names=OTHER_STRIP))
    assert "PowerMappingError" in str(exit_info.value)


# ---- a whole simulated night on a layout that is not Starfront's -----------------------------

class MappedNight:
    def __init__(self):
        self.folder = prepare_folder(None, installation=installation_with(OTHER))
        self.now = datetime.now(timezone.utc)
        self.rig = SimRig(self.folder, say=lambda t: None, clock=lambda: self.now, outlet_names=OTHER_STRIP)
        self.runner = build_sim_monitor(self.folder, self.rig)
        self.app, self.gate = self.runner.application, self.runner.gate
        self.app.mode.enable_hardware_execution()

    def cycles(self, count, seconds=5):
        for _ in range(count):
            self.now += timedelta(seconds=seconds)
            self.gate.cycle(now=self.now)


def test_a_roof_closure_on_a_non_starfront_layout_cuts_only_the_mapped_outlets():
    night = MappedNight()
    night.cycles(3)
    assert night.gate.arm()
    night.cycles(16)
    assert night.app.supervisor.session_state is SessionState.IMAGING_PERMITTED
    night.rig.set_roof("CLOSED")
    night.cycles(16)
    assert night.app.supervisor.session_state is SessionState.ABORTED
    assert night.rig.on == {1: False, 2: False, 3: False, 4: True, 5: True, 6: True}
    assert sorted(night.rig.cuts) == [1, 2, 3] and night.rig.cuts == [1, 2, 3]    # in shutdown order
    assert "outlet 6 (Control Mac): ON" in (night.folder / "strip.txt").read_text()


def test_even_a_mapping_that_bypassed_validation_cannot_switch_the_host_outlet():
    # Defence in depth: build a mapping by hand that names the host's own outlet as the ASIAIR target.
    from modules.guardian_v1_power_mapping import Outlet, PowerMapping
    host = Outlet(6, "Control Mac")
    broken = PowerMapping("kasa_hs300", host, {"asiair": host, "mount": Outlet(2, "AM5N"),
                                                 "accessories": Outlet(3, "Dew Box")})
    for make in (Strip, BatchStrip):
        strip = make(OTHER_STRIP)
        compose_mapped_kasa(host="h", mapping=broken, transport=strip).execute_safety_power(ALL_ROLES)
        assert strip.on[6] is True                                   # never switched
        assert strip.on[2] is False and strip.on[3] is False         # the legitimate targets still were
