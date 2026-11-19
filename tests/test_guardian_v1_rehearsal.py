import json

import pytest

from modules.guardian_types import SafetyPowerState as S
from modules.guardian_v1_rehearsal import (
    RehearsalRefused,
    SCENARIOS,
    preflight,
    run_rehearsal,
    write_evidence,
)

ALIASES = {1: "Mac Mini", 2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus"}


class FakeStrip:
    """In-memory HS300 with the same batch interface as PythonKasaTransport."""

    def __init__(self, on=(1, 2, 3, 4), refuse=(), unreadable=(), cuts_outlet_1=False):
        self.on = set(on)
        self.refuse = set(refuse)
        self.unreadable = set(unreadable)
        self.cuts_outlet_1 = cuts_outlet_1
        self.commands = []

    def check_outlet(self, number, alias):
        return ALIASES.get(number) == alias

    def get_outlet_state(self, number, alias):
        return S.ON if number in self.on else S.OFF

    def power_off_outlet(self, number, alias):
        return self.power_off_outlets([(number, alias)])[number]

    def get_outlet_states(self, requests):
        out = {}
        for number, alias in requests:
            if number in self.unreadable or ALIASES.get(number) != alias:
                out[number] = None
            else:
                out[number] = S.ON if number in self.on else S.OFF
        return out

    def power_off_outlets(self, requests):
        sent = {}
        for number, alias in requests:
            self.commands.append(number)
            if number in self.refuse:
                sent[number] = False
                continue
            self.on.discard(number)
            sent[number] = True
        if self.cuts_outlet_1:
            self.on.discard(1)
        return sent


def run(strip, scenario="roof-closed", **kw):
    return run_rehearsal(
        scenario=scenario, transport=strip, configuration_fingerprint="fp",
        sleep=lambda s: None, **kw)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_scenario_cuts_the_three_outlets_and_spares_the_mac(scenario):
    strip = FakeStrip()
    r = run(strip, scenario)
    assert r.passed, r.notes
    assert r.observed_triggers == [r.expected_trigger]
    assert strip.on == {1}
    assert r.outlets_after == {"2": "OFF", "3": "OFF", "4": "OFF"}
    assert r.protected_after == {"1": "ON"}
    assert r.session_state == "ABORTED"
    assert 1 not in strip.commands


def test_wrong_trigger_would_fail():
    r = run(FakeStrip(), "roof-closed")
    assert r.expected_trigger == "ROOF_CLOSED"


def test_a_refusing_outlet_fails_the_rehearsal():
    strip = FakeStrip(refuse={3})
    r = run(strip, max_cycles=3)
    assert not r.passed
    assert 3 in strip.on
    assert r.unresolved_actions


def test_cutting_the_mac_fails_the_rehearsal():
    r = run(FakeStrip(cuts_outlet_1=True))
    assert not r.passed
    assert r.protected_after == {"1": "OFF"}


def test_preflight_refuses_unreadable_target():
    with pytest.raises(RehearsalRefused):
        preflight(FakeStrip(unreadable={3}))


def test_preflight_refuses_unreadable_protected_outlet():
    with pytest.raises(RehearsalRefused):
        preflight(FakeStrip(unreadable={1}))


def test_preflight_refuses_when_all_targets_already_off():
    with pytest.raises(RehearsalRefused):
        preflight(FakeStrip(on={1}))
    assert preflight(FakeStrip(on={1}), allow_already_off=True)


def test_already_off_run_is_marked_weak_evidence():
    r = run(FakeStrip(on={1}), allow_already_off=True)
    assert r.weak_evidence


def test_refusal_switches_nothing():
    strip = FakeStrip(on={1})
    with pytest.raises(RehearsalRefused):
        run(strip)
    assert strip.commands == []


def test_unknown_scenario_refused():
    with pytest.raises(RehearsalRefused):
        run(FakeStrip(), "nonsense")


def test_evidence_file_never_authorizes_commissioning(tmp_path):
    strip = FakeStrip()
    r = run(strip)
    path = write_evidence(r, tmp_path, configuration_fingerprint="fp", kasa_host="h")
    data = json.loads(path.read_text())
    assert data["schema"] == "guardian-rehearsal-v1"
    assert data["commissioning_authorized"] is False
    assert data["passed"] is True
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_real_recovery_file_is_never_used(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    run(FakeStrip())
    assert list(tmp_path.rglob("*.json")) == []


class VerifyDisagrees(FakeStrip):
    """Verification read and the later independent read disagree."""

    def __init__(self, verify_says, final_says_on):
        super().__init__()
        self.verify_says = verify_says
        self.final_says_on = final_says_on
        self.cut = False
        self.reads_after_cut = 0

    def power_off_outlets(self, requests):
        sent = {n: True for n, _ in requests}
        self.cut = True
        if not self.final_says_on:
            self.on = {1}
        return sent

    def get_outlet_states(self, requests):
        real = super().get_outlet_states(requests)
        if not self.cut:
            return real
        self.reads_after_cut += 1
        if self.reads_after_cut == 1:  # the guardian's own verification read
            return {n: (S.OFF if self.verify_says == "off" else S.ON)
                    for n, _ in requests}
        return real


def test_independent_read_catches_an_outlet_still_on():
    strip = VerifyDisagrees("off", final_says_on=True)
    r = run(strip, max_cycles=4)
    assert not r.passed
    assert r.outlets_after["2"] == "ON"


def test_unresolved_actions_fail_even_if_outlets_end_up_off():
    strip = VerifyDisagrees("on", final_says_on=False)
    r = run(strip, max_cycles=1)
    assert r.unresolved_actions
    assert not r.passed


def test_wrong_trigger_fails_the_rehearsal(monkeypatch):
    import modules.guardian_v1_rehearsal as mod
    from modules.guardian_types import ProtectionTrigger
    monkeypatch.setitem(mod.EXPECTED_TRIGGER, "roof-closed",
                        ProtectionTrigger.UPS_LOW_BATTERY)
    r = run(FakeStrip())
    assert not r.passed
