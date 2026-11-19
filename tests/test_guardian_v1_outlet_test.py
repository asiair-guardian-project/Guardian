import pytest

from modules.guardian_types import SafetyPowerState
from modules import guardian_v1_outlet_test as ot
from modules.guardian_v1_outlet_test import CONFIRM_PHRASE, Environment

NAMES = {1: "Mac Mini", 2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus", 5: "Spare", 6: "Plug 6"}


class FakeStrip:
    """Simulated HS300 plus a transport with the same methods as the real Kasa transport."""

    def __init__(self, on=(1, 2, 3, 4, 5), names=None):
        self.names = dict(names or NAMES)
        self.on = {n: n in on for n in self.names}
        self.commands = []          # every switching command ever sent: (verb, number)
        self.off_does_nothing = False
        self.also_flip = None       # outlet that wrongly changes when outlet 5 is switched off
        self.on_fails = False
        self.verify_blind = False   # Guardian's verification read cannot see the outlet
        self.verify_lies = False    # Guardian's verification read always says OFF

    def outlets(self):
        return [{"number": n, "name": self.names[n], "is_on": self.on[n]} for n in sorted(self.names)]

    # --- transport used by Guardian 1.0 (off only)
    def check_outlet(self, number, alias):
        return self.names.get(number) == alias

    def get_outlet_state(self, number, alias):
        return SafetyPowerState.ON if self.on[number] else SafetyPowerState.OFF

    def power_off_outlet(self, number, alias):
        return self.power_off_outlets([(number, alias)])[number]

    def power_off_outlets(self, requests):
        results = {}
        for number, alias in requests:
            ok = self.names.get(number) == alias
            if ok:
                self.commands.append(("off", number))
                if not self.off_does_nothing:
                    self.on[number] = False
                if self.also_flip:
                    self.on[self.also_flip] = False
            results[number] = ok
        return results

    def get_outlet_states(self, requests):
        if self.verify_blind:
            return {n: None for n, a in requests}
        if self.verify_lies:
            return {n: SafetyPowerState.OFF for n, a in requests}
        return {n: (SafetyPowerState.ON if self.on[n] else SafetyPowerState.OFF)
                if self.names.get(n) == a else None for n, a in requests}

    # --- v0.6 controller (on)
    def switch_on(self, name):
        number = [n for n, v in self.names.items() if v == name][0]
        assert number != 1
        self.commands.append(("on", number))
        if self.on_fails:
            raise RuntimeError("could not switch on")
        self.on[number] = True


def make_env(strip, answer=CONFIRM_PHRASE):
    out = []
    env = Environment(
        read_outlets=strip.outlets, switch_on=strip.switch_on,
        power_off_via_v1=lambda alias: ot.v1_power_off(strip, alias),
        say=out.append, confirm=lambda prompt: answer, sleep=lambda s: None)
    return env, out


def test_pass_when_outlet_starts_on_and_everything_is_restored():
    strip = FakeStrip()
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 0
    assert ("off", 5) in strip.commands
    assert {c[1] for c in strip.commands} == {5}              # only outlet 5 was ever commanded
    assert strip.on == {1: True, 2: True, 3: True, 4: True, 5: True, 6: False}
    assert any("PASSED" in line for line in out)


def test_pass_when_outlet_starts_off_it_is_switched_on_first_then_left_off():
    strip = FakeStrip(on=(1, 2, 3, 4))
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 0
    assert strip.commands == [("on", 5), ("off", 5)]
    assert strip.on[5] is False and strip.on[1] and strip.on[2] and strip.on[3] and strip.on[4]


@pytest.mark.parametrize("number", [1, 2, 3, 4, 6, 7])
def test_only_outlet_5_can_ever_be_tested(number):
    strip = FakeStrip()
    env, out = make_env(strip)
    assert ot.run_test(env, number, NAMES.get(number, "x")) == 1
    assert strip.commands == []


@pytest.mark.parametrize("alias", ["Mac Mini", "ASIAIR", "Wave 150i", "Pegasus", "", "  ", "Wrong name"])
def test_refuses_protected_blank_or_wrong_names(alias):
    strip = FakeStrip()
    env, out = make_env(strip)
    assert ot.run_test(env, 5, alias) == 1
    assert strip.commands == []


def test_refuses_when_the_name_is_not_unique():
    strip = FakeStrip(names={**NAMES, 6: "Spare"})
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 1
    assert strip.commands == []


def test_refuses_when_a_protected_outlet_shares_the_name():
    strip = FakeStrip(names={**NAMES, 5: "Pegasus", 4: "Other"})
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Pegasus") == 1
    assert strip.commands == []


def test_wrong_confirmation_switches_nothing():
    strip = FakeStrip()
    env, out = make_env(strip, answer="yes")
    assert ot.run_test(env, 5, "Spare") == 1
    assert strip.commands == []


def test_fails_if_the_off_command_does_nothing_and_still_restores():
    strip = FakeStrip()
    strip.off_does_nothing = True
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("FAILED" in line for line in out)
    assert strip.on[5] is True


def test_fails_loudly_if_another_outlet_changes():
    strip = FakeStrip()
    strip.also_flip = 4
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("OTHER outlets changed" in line and "4" in line for line in out)


def test_restore_failure_is_reported():
    strip = FakeStrip()
    strip.on_fails = True
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("RESTORE FAILED" in line for line in out)


def test_exception_in_the_v1_path_still_restores_the_outlet():
    strip = FakeStrip(on=(1, 2, 3, 4))
    env, out = make_env(strip)

    real = env.power_off_via_v1
    calls = []

    def boom_once(alias):
        calls.append(alias)
        if len(calls) == 1:
            raise RuntimeError("strip unreachable")
        return real(alias)

    env.power_off_via_v1 = boom_once
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("could not finish" in line for line in out)
    assert strip.on[5] is False        # it started OFF, was switched ON for the test, and is OFF again


def test_a_restore_that_cannot_switch_off_is_reported_not_hidden():
    strip = FakeStrip(on=(1, 2, 3, 4))
    env, out = make_env(strip)

    def boom(alias):
        raise RuntimeError("strip unreachable")

    env.power_off_via_v1 = boom
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("RESTORE FAILED" in line for line in out)


def test_list_is_read_only():
    strip = FakeStrip()
    env, out = make_env(strip)
    assert ot.list_outlets(env) == 0
    assert strip.commands == []
    assert any("Spare" in line for line in out)


def _cli_without_hardware(monkeypatch, layout=None):
    import guardian_v1_outlet_test as cli
    from modules.guardian_v1_layout import starfront_layout
    monkeypatch.setattr(cli, "kasa_host_from_monitor_plist", lambda: "192.0.2.1")
    monkeypatch.setattr(cli, "layout_from_monitor_plist", lambda: layout or starfront_layout())
    contacted = []
    monkeypatch.setattr(cli, "real_environment", lambda *a, **k: contacted.append(1) or (_ for _ in ()).throw(
        AssertionError("the strip must not be contacted for a refused outlet")))
    return cli, contacted


def test_cli_rejects_other_outlet_numbers(monkeypatch, capsys):
    cli, contacted = _cli_without_hardware(monkeypatch)
    for number in ("4", "1", "6"):
        assert cli.main(["test", "--outlet", number, "--expect-alias", "Pegasus"]) == 1
    assert "REFUSED" in capsys.readouterr().out and not contacted


def test_fails_when_guardian_cannot_verify_even_though_the_outlet_is_off():
    strip = FakeStrip()
    strip.verify_blind = True
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("did not report VERIFIED_OFF" in line for line in out)


def test_independent_read_catches_a_verification_that_lies():
    strip = FakeStrip()
    strip.off_does_nothing = True
    strip.verify_lies = True
    env, out = make_env(strip)
    assert ot.run_test(env, 5, "Spare") == 1
    assert any("NOT off" in line for line in out)
    assert not any("did not report VERIFIED_OFF" in line for line in out)


# ---- --pause (check the outlet in the Kasa app between steps) ----------------------

def make_env_with_pauses(strip, calls, events=None):
    env, out = make_env(strip)
    env.pause = lambda prompt: calls.append(prompt)
    return env, out


def test_without_pause_flag_it_never_stops_to_ask():
    strip = FakeStrip()
    calls = []
    env, out = make_env_with_pauses(strip, calls)
    assert ot.run_test(env, 5, "Spare") == 0
    assert calls == []


def test_pause_checkpoints_when_starting_off():
    strip = FakeStrip(on=(1, 2, 3, 4))
    calls, states_at_pause = [], []
    env, out = make_env(strip)
    env.pause = lambda prompt: (calls.append(prompt), states_at_pause.append(strip.on[5]))
    assert ot.run_test(env, 5, "Spare", pause=True) == 0
    assert len(calls) == 2
    assert states_at_pause == [True, False]       # really ON at the first look, really OFF at the second
    text = "\n".join(out)
    assert "Confirmed by a fresh read: outlet 5 is ON" in text
    assert "Confirmed by an independent fresh read: outlet 5 is OFF" in text


def test_pause_checkpoints_when_starting_on():
    strip = FakeStrip()
    states_at_pause = []
    env, out = make_env(strip)
    env.pause = lambda prompt: states_at_pause.append(strip.on[5])
    assert ot.run_test(env, 5, "Spare", pause=True) == 0
    assert states_at_pause == [True, False, True]  # ON, OFF, then ON again after restoring
    assert strip.on[5] is True


def test_ctrl_c_at_a_pause_still_puts_the_outlet_back():
    strip = FakeStrip(on=(1, 2, 3, 4, 5))
    env, out = make_env(strip)
    answers = iter([None, KeyboardInterrupt])

    def pause(prompt):
        item = next(answers)
        if item is KeyboardInterrupt:
            raise KeyboardInterrupt

    env.pause = pause
    with pytest.raises(KeyboardInterrupt):
        ot.run_test(env, 5, "Spare", pause=True)
    assert strip.on[5] is True           # restored to its starting state (ON)


def test_ctrl_c_at_the_first_pause_leaves_a_started_off_outlet_off():
    strip = FakeStrip(on=(1, 2, 3, 4))
    env, out = make_env(strip)

    def pause(prompt):
        raise KeyboardInterrupt

    env.pause = pause
    with pytest.raises(KeyboardInterrupt):
        ot.run_test(env, 5, "Spare", pause=True)
    # outlet was switched ON for the test; it must not be left ON when it started OFF
    assert strip.on[5] is False


def test_cli_accepts_pause_flag(monkeypatch):
    cli, contacted = _cli_without_hardware(monkeypatch)
    assert cli.main(["test", "--pause", "--outlet", "3", "--expect-alias", "x"]) == 1   # parsed; outlet 3 refused
    assert not contacted
