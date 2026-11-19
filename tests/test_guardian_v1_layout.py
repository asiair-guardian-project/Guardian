"""The commissioning tools follow the operator's outlet mapping (and the Starfront wiring when there is none)."""
import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from dli_fake import FakeDli  # noqa: E402
from test_guardian_v1_outlet_test import FakeStrip  # noqa: E402

import guardian_v1_evidence_audit as audit_cli  # noqa: E402
from modules import guardian_v1_outlet_test as ot  # noqa: E402
from modules.guardian_v1_dli_transport import DigitalLoggersTransport  # noqa: E402
from modules.guardian_v1_layout import layout_from_installation, starfront_layout  # noqa: E402
from modules.guardian_v1_outlet_test import Environment, OutletTestRefused  # noqa: E402

KASA = {"power": {"type": "kasa_hs300", "host_outlet": {"number": 6, "alias": "Control Mac"},
                  "targets": {"asiair": {"number": 1, "alias": "Air Plus"}, "mount": {"number": 2, "alias": "AM5N"},
                              "accessories": {"number": 3, "alias": "Dew Box"}}}}
DLI = {"power": {**KASA["power"], "type": "digital_loggers_rest", "host_outlet": {"number": 1, "alias": "Mac"},
                 "targets": {"asiair": {"number": 2, "alias": "ASIAIR"}, "mount": {"number": 3, "alias": "Mount"},
                             "accessories": {"number": 4, "alias": "Dew"}}}}
KASA_NAMES = {1: "Air Plus", 2: "AM5N", 3: "Dew Box", 4: "Spare4", 5: "Spare5", 6: "Control Mac"}


def test_no_power_section_is_the_starfront_layout():
    layout = layout_from_installation({})
    assert layout == starfront_layout() and layout.allowed_test_outlets() == (5,)
    assert [t.number for t in layout.targets] == [2, 3, 4] and layout.host == (1, "Mac Mini")


def test_a_mapped_layout_protects_every_mapped_outlet_and_allows_only_spares():
    layout = layout_from_installation(KASA)
    assert layout.protected_numbers == {1, 2, 3, 6} and layout.allowed_test_outlets() == (4, 5)
    assert layout.protected_aliases == {"Air Plus", "AM5N", "Dew Box", "Control Mac"}
    assert [t.endpoint for t in layout.targets] == ["1_asiair", "2_mount", "3_accessories"]


# ---- the outlet live test with a mapped Kasa strip ---------------------------------------------

def _env(strip, layout, outlet):
    out = []
    return Environment(
        read_outlets=strip.outlets, switch_on=strip.switch_on,
        power_off_via_v1=lambda alias: ot.v1_power_off(strip, alias, outlet, layout.controller_id),
        say=out.append, confirm=lambda prompt: f"OUTLET {outlet} IS EMPTY", sleep=lambda s: None), out


def test_a_spare_outlet_can_be_tested_on_a_mapped_strip_and_nothing_else_is_touched():
    layout = layout_from_installation(KASA)
    strip = FakeStrip(on=(1, 2, 3, 4, 5, 6), names=KASA_NAMES)
    strip.switch_on = lambda name: strip.on.__setitem__([n for n, v in strip.names.items() if v == name][0], True)
    env, out = _env(strip, layout, 4)
    assert ot.run_test(env, 4, "Spare4", layout=layout) == 0
    assert {c[1] for c in strip.commands} == {4}
    assert strip.on == {1: True, 2: True, 3: True, 4: True, 5: True, 6: True}   # all back as they started


@pytest.mark.parametrize("number,alias", [(1, "Air Plus"), (2, "AM5N"), (3, "Dew Box"), (6, "Control Mac"),
                                            (7, "x"), (0, "x")])
def test_mapped_outlets_and_the_host_can_never_be_tested(number, alias):
    layout = layout_from_installation(KASA)
    strip = FakeStrip(on=(1, 2, 3, 4, 5, 6), names=KASA_NAMES)
    env, out = _env(strip, layout, number)
    assert ot.run_test(env, number, alias, layout=layout) == 1 and strip.commands == []


def test_a_spare_named_like_a_mapped_outlet_is_refused():
    layout = layout_from_installation(KASA)
    names = {**KASA_NAMES, 4: "AM5N"}
    strip = FakeStrip(on=(1, 2, 3, 4, 5, 6), names=names)
    env, out = _env(strip, layout, 4)
    assert ot.run_test(env, 4, "AM5N", layout=layout) == 1 and strip.commands == []


def test_starfront_outlet_five_rule_is_unchanged():
    strip = FakeStrip()
    env, out = _env(strip, starfront_layout(), 5)
    for bad in (4, 6):
        assert ot.run_test(env, bad, "x") == 1
    assert strip.commands == []


# ---- the outlet live test on a simulated Digital Loggers unit ---------------------------------

def test_the_dli_outlet_test_passes_on_a_spare_and_leaves_everything_else_alone():
    fake = FakeDli(["Mac", "ASIAIR", "Mount", "Dew", "Spare5", "s6", "s7", "s8"]).start()
    try:
        layout = layout_from_installation(DLI)
        transport = DigitalLoggersTransport(host="127.0.0.1", port=fake.port, username="admin", password="secret")
        out = []
        env = ot.real_environment_dli("127.0.0.1", layout, 5, say=out.append,
                                      confirm=lambda p: "OUTLET 5 IS EMPTY", sleep=lambda s: None, transport=transport)
        assert ot.run_test(env, 5, "Spare5", layout=layout) == 0, out
        assert fake.on == [True] * 8                                   # everything back as it started
        switched = {p for m, p, f in fake.log if m == "PUT"}
        assert switched == {"/restapi/relay/outlets/=4/state/"}          # only outlet 5 (index 4) was commanded
    finally:
        fake.stop()


def test_the_dli_outlet_test_refuses_a_mapped_outlet_before_switching_anything():
    fake = FakeDli(["Mac", "ASIAIR", "Mount", "Dew", "Spare5", "s6", "s7", "s8"]).start()
    try:
        layout = layout_from_installation(DLI)
        transport = DigitalLoggersTransport(host="127.0.0.1", port=fake.port, username="admin", password="secret")
        env = ot.real_environment_dli("127.0.0.1", layout, 3, say=lambda s: None,
                                      confirm=lambda p: "OUTLET 3 IS EMPTY", sleep=lambda s: None, transport=transport)
        assert ot.run_test(env, 3, "Mount", layout=layout) == 1
        assert not [1 for m, p, f in fake.log if m == "PUT"]
    finally:
        fake.stop()


def test_power_on_for_test_is_used_only_by_the_outlet_test():
    root = Path(__file__).resolve().parent.parent
    users = [str(p.relative_to(root)) for p in list(root.glob("*.py")) + list((root / "modules").glob("*.py"))
             if "power_on_outlet_for_test" in p.read_text()]
    assert sorted(users) == ["modules/guardian_v1_dli_transport.py", "modules/guardian_v1_outlet_test.py"]


# ---- the evidence audit -------------------------------------------------------------------------

def _plist(path):
    argv = ["python", "guardian_v1.py", "--continuous-monitor"]
    for key, value in [("--recovery-file", "/t/state.json"), ("--operator-socket", "/t/op.sock"),
                       ("--asiair-host", "192.0.2.10"), ("--alpaca-host", "alpaca.example"),
                       ("--alpaca-port", "443"), ("--alpaca-device", "1")]:
        argv += [key, value]
    path.write_bytes(plistlib.dumps({"ProgramArguments": argv, "RunAtLoad": True, "KeepAlive": False}))
    return path


def test_audit_reports_the_operators_own_outlets(tmp_path):
    report = audit_cli.audit(_plist(tmp_path / "a.plist"), "192.0.2.20", KASA)
    targets = report["configuration"]["targets"]
    assert {t["outlet"] for t in targets.values()} == {1, 2, 3}
    assert targets["ASIAIR"]["alias"] == "Air Plus"
    assert report["configuration"]["host_outlet"] == {"outlet": 6, "alias": "Control Mac"}
    assert not report["hardware_authorized"] and report["execution_commands"] == 0


def test_audit_fingerprint_changes_with_the_mapping_and_the_controller_type(tmp_path):
    plist = _plist(tmp_path / "a.plist")
    base = audit_cli.audit(plist, "192.0.2.20", KASA)["configuration_fingerprint_sha256"]
    renamed = {"power": {**KASA["power"], "targets": {**KASA["power"]["targets"],
                                                       "mount": {"number": 2, "alias": "AM5N-2"}}}}
    assert audit_cli.audit(plist, "192.0.2.20", renamed)["configuration_fingerprint_sha256"] != base
    other_type = {"power": {**KASA["power"], "type": "digital_loggers_rest"}}
    assert audit_cli.audit(plist, "192.0.2.20", other_type)["configuration_fingerprint_sha256"] != base


def test_starfront_audit_fingerprint_is_unchanged(tmp_path):
    plist = _plist(tmp_path / "a.plist")
    assert "host_outlet" not in audit_cli.audit(plist, "192.0.2.20")["configuration"]
    assert audit_cli.audit(plist, "192.0.2.20") == audit_cli.audit(plist, "192.0.2.20", {})
    # pinned from the code before the layout change: the Starfront fingerprint must never move
    assert audit_cli.audit(plist, "192.0.2.20")["configuration_fingerprint_sha256"] == \
        "911ff3ddbfc3e619384e5e1c784c08e874a77e0fa47372d83139c9f5d63889f6"


def test_a_mapped_outlet_is_refused_by_number_even_if_the_strip_calls_it_something_else():
    layout = layout_from_installation(KASA)              # outlet 2 is the mount ("AM5N") in the mapping
    strip = FakeStrip(on=(1, 2, 3, 4, 5, 6), names={**KASA_NAMES, 2: "Renamed in the app"})
    env, out = _env(strip, layout, 2)
    assert ot.run_test(env, 2, "Renamed in the app", layout=layout) == 1
    assert strip.commands == []
