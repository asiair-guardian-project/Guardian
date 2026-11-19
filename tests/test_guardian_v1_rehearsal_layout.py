"""The commissioning rehearsal (a REAL power cut) follows the operator's mapping, on Kasa and Digital Loggers."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from dli_fake import FakeDli  # noqa: E402

import modules.guardian_v1_rehearsal as rh  # noqa: E402
from modules.guardian_types import SafetyPowerState as S  # noqa: E402
from modules.guardian_v1_dli_transport import DigitalLoggersTransport  # noqa: E402
from modules.guardian_v1_layout import layout_from_installation, starfront_layout  # noqa: E402
from modules.guardian_v1_rehearsal_cli import main  # noqa: E402

KASA = {"kasa": {"power_strip_ip": "192.0.2.20"},
        "power": {"type": "kasa_hs300", "host_outlet": {"number": 6, "alias": "Control Mac"},
                  "targets": {"asiair": {"number": 1, "alias": "Air Plus"}, "mount": {"number": 2, "alias": "AM5N"},
                              "accessories": {"number": 3, "alias": "Dew Box"}}}}
NAMES = {1: "Air Plus", 2: "AM5N", 3: "Dew Box", 4: "Spare4", 5: "Spare5", 6: "Control Mac"}


class MappedStrip:
    """In-memory strip with the operator's own names, same batch interface as the real Kasa transport."""

    def __init__(self, on=(1, 2, 3, 6), cuts=None):
        self.on, self.commands, self.cuts = set(on), [], cuts

    def check_outlet(self, number, alias):
        return NAMES.get(number) == alias

    def get_outlet_state(self, number, alias):
        return S.ON if number in self.on else S.OFF

    def power_off_outlet(self, number, alias):
        return self.power_off_outlets([(number, alias)])[number]

    def get_outlet_states(self, requests):
        return {n: (S.ON if n in self.on else S.OFF) if NAMES.get(n) == a else None for n, a in requests}

    def power_off_outlets(self, requests):
        sent = {}
        for number, alias in requests:
            self.commands.append(number)
            self.on.discard(number)
            sent[number] = NAMES.get(number) == alias
        if self.cuts:
            self.on.discard(self.cuts)
        return sent


def test_the_confirm_token_names_the_operators_outlets():
    assert starfront_layout().confirm_token == "CUT_OUTLETS_2_3_4"
    assert layout_from_installation(KASA).confirm_token == "CUT_OUTLETS_1_2_3"


@pytest.mark.parametrize("scenario", rh.SCENARIOS)
def test_every_scenario_cuts_only_the_operators_three_outlets_and_spares_the_host(scenario):
    layout = layout_from_installation(KASA)
    strip = MappedStrip()
    result = rh.run_rehearsal(scenario=scenario, transport=strip, configuration_fingerprint="fp",
                              sleep=lambda s: None, layout=layout)
    assert result.passed, result.notes
    assert strip.on == {6}
    assert set(strip.commands) == {1, 2, 3} and 6 not in strip.commands
    assert result.outlets_after == {"1": "OFF", "2": "OFF", "3": "OFF"}
    assert result.protected_after == {"6": "ON"}


def test_cutting_the_host_computer_fails_the_rehearsal():
    layout = layout_from_installation(KASA)
    strip = MappedStrip(cuts=6)
    result = rh.run_rehearsal(scenario="roof-closed", transport=strip, configuration_fingerprint="fp",
                              sleep=lambda s: None, layout=layout)
    assert not result.passed


def test_preflight_refuses_a_strip_whose_names_do_not_match_the_mapping():
    layout = layout_from_installation(KASA)
    strip = MappedStrip()
    strip.get_outlet_states = lambda reqs: {n: None for n, a in reqs}
    with pytest.raises(rh.RehearsalRefused):
        rh.preflight(strip, layout=layout)
    assert strip.commands == []


def _cli(tmp_path, installation, transport, argv, answer="CUT"):
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(yaml.safe_dump(installation))
    lines = []
    args = ["--installation-config", str(yaml_path), "--kasa-host", installation["kasa"]["power_strip_ip"],
            "--evidence-dir", str(tmp_path / "ev"), "--operator-socket", str(tmp_path / "none.sock")] + argv
    code = main(args, transport=transport, input_fn=lambda _p: answer, out=lines.append, v06_check=lambda _r: False)
    return code, "\n".join(lines)


def test_cli_dry_run_tells_the_operator_the_right_token_and_switches_nothing(tmp_path):
    strip = MappedStrip()
    code, text = _cli(tmp_path, KASA, strip, ["--dry-run"])
    assert code == 0 and strip.commands == [] and "--confirm CUT_OUTLETS_1_2_3" in text


def test_cli_refuses_the_starfront_token_on_a_mapped_strip(tmp_path):
    strip = MappedStrip()
    code, text = _cli(tmp_path, KASA, strip, ["--confirm", "CUT_OUTLETS_2_3_4"])
    assert code == 2 and strip.commands == []


def test_cli_full_run_on_a_mapped_strip(tmp_path):
    strip = MappedStrip()
    code, text = _cli(tmp_path, KASA, strip, ["--confirm", "CUT_OUTLETS_1_2_3"])
    assert code == 0 and "PASS" in text and "outlets 1, 2 and 3" in text and strip.on == {6}


# ---- a simulated Digital Loggers unit, through the real transport -------------------------------

DLI_NAMES = ["Mac", "ASIAIR", "Mount", "Dew", "Spare5", "s6", "s7", "s8"]
DLI = {"kasa": {"power_strip_ip": "127.0.0.1"},
       "power": {"type": "digital_loggers_rest", "host_outlet": {"number": 1, "alias": "Mac"},
                 "targets": {"asiair": {"number": 2, "alias": "ASIAIR"}, "mount": {"number": 3, "alias": "Mount"},
                             "accessories": {"number": 4, "alias": "Dew"}}}}


def test_a_full_rehearsal_on_a_simulated_digital_loggers_unit():
    fake = FakeDli(DLI_NAMES).start()
    try:
        transport = DigitalLoggersTransport(host="127.0.0.1", port=fake.port, username="admin", password="secret")
        result = rh.run_rehearsal(scenario="roof-closed", transport=transport, configuration_fingerprint="fp",
                                  sleep=lambda s: None, layout=layout_from_installation(DLI))
        assert result.passed, result.notes
        assert fake.on == [True, False, False, False, True, True, True, True]
        switched = [p for m, p, f in fake.log if m == "PUT"]
        assert switched == [f"/restapi/relay/outlets/={i}/state/" for i in (1, 2, 3)]      # ASIAIR, mount, dew; never host
    finally:
        fake.stop()


def test_a_digital_loggers_rehearsal_fails_when_a_relay_does_not_move():
    fake = FakeDli(DLI_NAMES).start()
    fake.stuck.add(2)
    try:
        transport = DigitalLoggersTransport(host="127.0.0.1", port=fake.port, username="admin", password="secret")
        result = rh.run_rehearsal(scenario="roof-closed", transport=transport, configuration_fingerprint="fp",
                                  sleep=lambda s: None, layout=layout_from_installation(DLI))
        assert not result.passed
    finally:
        fake.stop()
