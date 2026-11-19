"""Digital Loggers support, against a simulated controller only (no real unit has been tested)."""
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from dli_fake import FakeDli  # noqa: E402

import guardian_v1_dli_probe as probe  # noqa: E402
from modules.guardian_types import SafetyPowerRole as Role, SafetyPowerState  # noqa: E402
from modules.guardian_v1_dli_transport import (  # noqa: E402
    DigitalLoggersTransport, DliTransportError, dli_credentials,
)
from modules.guardian_v1_mapped_kasa import compose_mapped_kasa  # noqa: E402
from modules.guardian_v1_power_mapping import PowerMappingError, parse_power_section  # noqa: E402
import modules.guardian_v1_setup_wizard as wizard  # noqa: E402

NAMES = ["Mac", "ASIAIR", "Mount", "Dew", "Spare5", "Spare6", "Spare7", "Spare8"]
SECTION = {"type": "digital_loggers_rest", "host_outlet": {"number": 1, "alias": "Mac"},
           "targets": {"asiair": {"number": 2, "alias": "ASIAIR"}, "mount": {"number": 3, "alias": "Mount"},
                       "accessories": {"number": 4, "alias": "Dew"}}}
ALL_ROLES = {Role.ASIAIR, Role.MOUNT, Role.ACCESSORIES}


@pytest.fixture
def dli():
    fake = FakeDli(NAMES).start()
    yield fake
    fake.stop()


def transport(fake, password="secret"):
    return DigitalLoggersTransport(host="127.0.0.1", port=fake.port, username="admin", password=password)


def puts(fake):
    return [(p, f) for m, p, f in fake.log if m == "PUT"]


# ---- the transport ---------------------------------------------------------------------------

def test_reads_name_and_state_and_numbers_are_one_based_while_the_api_is_zero_based(dli):
    t = transport(dli)
    assert t.check_outlet(3, "Mount") is True
    assert t.get_outlet_state(3, "Mount") is SafetyPowerState.ON
    assert any(p == "/restapi/relay/outlets/=2/name/" for m, p, f in dli.log)


def test_power_off_sends_a_form_encoded_false_with_the_csrf_header_and_switches_only_that_outlet(dli):
    assert transport(dli).power_off_outlet(3, "Mount") is True
    assert puts(dli) == [("/restapi/relay/outlets/=2/state/", {"value": "false"})]
    assert dli.on == [True, True, False, True, True, True, True, True]


def test_a_missing_csrf_header_is_a_failure_not_a_cut(dli):
    dli.require_csrf = False                                          # (the fake only enforces it when asked)
    dli.require_csrf = True
    t = transport(dli)
    t_conn = t._session()
    status, _ = t_conn.request("PUT", "/restapi/relay/outlets/=2/state/", form={"value": "false"})
    assert status == 204                                              # header is sent by default
    t.close()


def test_wrong_password_is_refused_and_nothing_is_switched(dli):
    with pytest.raises(DliTransportError):
        transport(dli, password="wrong").power_off_outlet(2, "ASIAIR")
    assert puts(dli) == [] and all(dli.on)


def test_a_renamed_outlet_is_refused_and_no_command_is_sent(dli):
    dli.names[2] = "Something else"
    with pytest.raises(DliTransportError):
        transport(dli).power_off_outlet(3, "Mount")
    assert puts(dli) == [] and dli.on[2] is True


def test_name_comparison_is_exact(dli):
    for wrong in ("mount", "Mount ", "MOUNT"):
        with pytest.raises(DliTransportError):
            transport(dli).power_off_outlet(3, wrong)
    assert puts(dli) == []


def test_batch_uses_one_connection_keeps_order_and_isolates_a_bad_outlet(dli):
    dli.names[2] = "renamed"
    result = transport(dli).power_off_outlets([(2, "ASIAIR"), (3, "Mount"), (4, "Dew")])
    assert result == {2: True, 3: False, 4: True}
    assert [p for p, f in puts(dli)] == ["/restapi/relay/outlets/=1/state/", "/restapi/relay/outlets/=3/state/"]
    assert dli.connections == 1                                       # one TCP connection for the whole batch
    assert dli.on[2] is True


def test_state_is_read_from_the_relay_and_a_stuck_relay_is_not_reported_off(dli):
    dli.stuck.add(1)
    t = transport(dli)
    assert t.power_off_outlets([(2, "ASIAIR")]) == {2: True}          # the command was sent...
    assert t.get_outlet_states([(2, "ASIAIR")]) == {2: SafetyPowerState.ON}   # ...but the relay never moved


def test_an_error_answer_to_the_off_command_counts_as_not_sent(dli):
    dli.fail_put.add(1)
    assert transport(dli).power_off_outlets([(2, "ASIAIR"), (3, "Mount")]) == {2: False, 3: True}


def test_an_unrecognised_state_reply_is_unknown_never_off(dli):
    dli.garbage_state = True
    assert transport(dli).get_outlet_states([(2, "ASIAIR")]) == {2: None}
    with pytest.raises(DliTransportError):
        transport(dli).get_outlet_state(2, "ASIAIR")


def test_a_reply_with_more_than_one_value_is_not_trusted(dli):
    dli.two_values = True
    assert transport(dli).get_outlet_states([(2, "ASIAIR")]) == {2: None}
    assert transport(dli).power_off_outlets([(2, "ASIAIR")]) == {2: False}
    assert dli.on[1] is True


def test_an_unreachable_controller_reports_unknown_and_not_sent(dli):
    t = DigitalLoggersTransport(host="127.0.0.1", port=1, username="a", password="b", timeout_seconds=1)
    assert t.get_outlet_states([(2, "ASIAIR")]) == {2: None}
    assert t.power_off_outlets([(2, "ASIAIR")]) == {2: False}


def test_outlet_numbers_outside_one_to_eight_are_refused(dli):
    for bad in (0, 9, True, "2"):
        with pytest.raises(DliTransportError):
            transport(dli).check_outlet(bad, "x")


def test_switching_a_real_address_is_blocked_under_automated_tests(monkeypatch):
    monkeypatch.delenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", raising=False)
    t = DigitalLoggersTransport(host="192.0.2.50", username="a", password="b")
    with pytest.raises(DliTransportError):
        t.power_off_outlet(2, "ASIAIR")
    with pytest.raises(DliTransportError):
        t.power_off_outlets([(2, "ASIAIR")])


def test_survey_is_read_only(dli):
    rows = transport(dli).survey()
    assert [r[1] for r in rows] == NAMES and puts(dli) == []


def test_credentials_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DLI_USERNAME", "u")
    monkeypatch.setenv("DLI_PASSWORD", "p")
    assert dli_credentials() == ("u", "p")


def test_missing_credentials_are_reported(monkeypatch):
    monkeypatch.delenv("DLI_USERNAME", raising=False)
    monkeypatch.delenv("DLI_PASSWORD", raising=False)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(OSError("no security tool")))
    with pytest.raises(DliTransportError):
        dli_credentials()


# ---- mapping ---------------------------------------------------------------------------------

def test_the_dli_mapping_allows_eight_outlets_and_optional_scheme_and_port():
    ok = {**SECTION, "targets": {**SECTION["targets"], "accessories": {"number": 8, "alias": "Dew"}},
          "scheme": "https", "port": 8443}
    mapping = parse_power_section(ok)
    assert mapping.targets["accessories"].number == 8 and dict(mapping.options) == {"scheme": "https", "port": 8443}


@pytest.mark.parametrize("change", [
    {"scheme": "ftp"}, {"port": 0}, {"port": "80"}, {"port": True}, {"bogus": 1},
])
def test_bad_dli_options_are_refused(change):
    with pytest.raises(PowerMappingError):
        parse_power_section({**SECTION, **change})


def test_kasa_still_has_six_outlets_and_refuses_dli_options():
    kasa = {**SECTION, "type": "kasa_hs300"}
    assert parse_power_section(kasa)
    with pytest.raises(PowerMappingError):
        parse_power_section({**kasa, "targets": {**kasa["targets"], "mount": {"number": 7, "alias": "Mount"}}})
    with pytest.raises(PowerMappingError):
        parse_power_section({**kasa, "scheme": "https"})


# ---- the whole shutdown on the simulated controller -------------------------------------------

def test_shutdown_cuts_asiair_mount_accessories_in_order_and_never_the_host_or_spares(dli):
    wiring = compose_mapped_kasa(host="127.0.0.1", mapping=parse_power_section(SECTION), transport=transport(dli))
    result = wiring.execute_safety_power(ALL_ROLES)
    assert dli.on == [True, False, False, False, True, True, True, True]
    assert [p for p, f in puts(dli)] == [f"/restapi/relay/outlets/={i}/state/" for i in (1, 2, 3)]
    assert {r.role: r.result.name for r in result} == {r: "VERIFIED_OFF" for r in ALL_ROLES}


def test_the_host_outlet_is_never_switched_even_if_a_target_points_at_it(dli):
    from modules.guardian_v1_power_mapping import Outlet, PowerMapping
    host = Outlet(1, "Mac")
    broken = PowerMapping("digital_loggers_rest", host, {"asiair": host, "mount": Outlet(3, "Mount"),
                                                         "accessories": Outlet(4, "Dew")}, {})
    compose_mapped_kasa(host="127.0.0.1", mapping=broken, transport=transport(dli)).execute_safety_power(ALL_ROLES)
    assert dli.on[0] is True and dli.on[2] is False


def test_a_renamed_outlet_during_shutdown_leaves_that_outlet_on_and_unverified(dli):
    dli.names[2] = "renamed"
    result = compose_mapped_kasa(host="127.0.0.1", mapping=parse_power_section(SECTION),
                                 transport=transport(dli)).execute_safety_power(ALL_ROLES)
    assert dli.on[2] is True
    assert {r.role: r.result.name for r in result}[Role.MOUNT] != "VERIFIED_OFF"


def test_a_stuck_relay_is_never_reported_verified_off(dli):
    dli.stuck.add(2)
    result = compose_mapped_kasa(host="127.0.0.1", mapping=parse_power_section(SECTION),
                                 transport=transport(dli)).execute_safety_power(ALL_ROLES)
    assert {r.role: r.result.name for r in result}[Role.MOUNT] != "VERIFIED_OFF"


def test_with_no_injected_transport_the_dli_type_builds_the_dli_transport(monkeypatch):
    monkeypatch.setenv("DLI_USERNAME", "u")
    monkeypatch.setenv("DLI_PASSWORD", "p")
    wiring = compose_mapped_kasa(host="127.0.0.1", mapping=parse_power_section(SECTION))
    adapter = next(iter(wiring.adapters.values()))
    assert type(adapter._transport._transport).__name__ == "DigitalLoggersTransport"


# ---- the probe -------------------------------------------------------------------------------

def _config(tmp_path, section=SECTION):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({"kasa": {"power_strip_ip": "127.0.0.1"}, "power": section}))
    return str(path)


def test_probe_reports_matches_and_sends_only_reads(dli, tmp_path):
    lines = []
    assert probe.main(["--config", _config(tmp_path)], transport=transport(dli), out=lines.append) == 0
    assert puts(dli) == [] and any("All mapped outlets match" in l for l in lines)


def test_probe_flags_a_name_mismatch(dli, tmp_path):
    dli.names[3] = "other"
    lines = []
    assert probe.main(["--config", _config(tmp_path)], transport=transport(dli), out=lines.append) == 1
    assert any("DOES NOT MATCH" in l for l in lines)


def test_probe_source_cannot_switch_anything():
    source = Path(probe.__file__).read_text()
    assert not re.search(r"PUT|power_off|_switch_off|\.request\(", source)


# ---- the wizard ------------------------------------------------------------------------------

FORM = {"asiair_ip": "192.0.2.10", "roof_host": wizard.DEFAULT_ALPACA_HOST, "roof_port": 443, "roof_device": 1,
        "strip_ip": "192.0.2.20", "host_outlet_number": 1, "host_outlet_alias": "Mac",
        "asiair_outlet_number": 2, "asiair_outlet_alias": "ASIAIR", "mount_outlet_number": 3,
        "mount_outlet_alias": "Mount", "accessories_outlet_number": 8, "accessories_outlet_alias": "Dew"}


def test_the_wizard_builds_a_digital_loggers_section_with_outlets_up_to_eight():
    installation = wizard.build_installation({**FORM, "controller": "digital_loggers_rest"})
    assert installation["power"]["type"] == "digital_loggers_rest"
    assert installation["power"]["targets"]["accessories"]["number"] == 8


def test_the_wizard_still_defaults_to_kasa_and_refuses_outlet_eight_there():
    with pytest.raises(wizard.WizardError):
        wizard.build_installation(FORM)
    assert wizard.build_installation({**FORM, "accessories_outlet_number": 4})["power"]["type"] == "kasa_hs300"


def test_the_wizard_refuses_an_unknown_controller():
    with pytest.raises(wizard.WizardError):
        wizard.build_installation({**FORM, "controller": "mystery"})


def test_next_steps_say_untested_for_digital_loggers_and_never_ask_for_credentials():
    inst = wizard.build_installation({**FORM, "controller": "digital_loggers_rest"})
    text = " ".join(wizard.next_steps("/x", inst))
    assert "NOT been tested" in text and "never asks for them" in text
    assert "Kasa account sign-in" not in text
    assert "Kasa account sign-in" in " ".join(wizard.next_steps("/x"))


def test_the_candidate_file_never_holds_credentials(tmp_path):
    inst = wizard.build_installation({**FORM, "controller": "digital_loggers_rest"})
    written = wizard.write_candidate(tmp_path, inst)
    assert not re.search(r"password|username|secret", Path(written["path"]).read_text(), re.I)
