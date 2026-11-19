"""Live test of Guardian 1.0's real power-off path on ONE spare outlet (outlet 5).

Purpose: prove that v1.0's own shutdown code (SafetyPowerManager -> Kasa adapter ->
python-kasa transport, the same path an emergency uses) really switches an outlet off
and verifies it, WITHOUT going near the ASIAIR, mount, Pegasus or the Mac mini.

Safety rules, all enforced here:
  * only outlet 5 can ever be tested; outlets 1-4 are refused by number and by name;
  * the outlet's name must match the one you give, and must be unique on the strip;
  * you must type a confirmation that the outlet has nothing plugged into it;
  * every other outlet is read before and after, and any change is reported as a failure;
  * the outlet is put back in the state it started in, even when the test fails.
Powering an outlet back ON uses the existing v0.6 Kasa controller (v1.0 itself never
switches power on); that controller refuses to switch outlet 1 as well.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from modules.guardian_types import SafetyPowerResult, SafetyPowerRole
from modules.guardian_v1_layout import Layout, starfront_layout

TEST_OUTLET = 5
PROTECTED_NUMBERS = frozenset({1, 2, 3, 4})
PROTECTED_ALIASES = frozenset({"Mac Mini", "ASIAIR", "Wave 150i", "Pegasus"})
CONFIRM_PHRASE = "OUTLET 5 IS EMPTY"
CONTROLLER_ID = "starfront_hs300"
ENDPOINT_ID = "spare_outlet_test"


class OutletTestRefused(Exception):
    """The test was not started; nothing was switched."""


@dataclass
class Environment:
    read_outlets: Callable[[], List[dict]]        # [{"number","name","is_on"}]
    switch_on: Callable[[str], None]              # v0.6 controller, by outlet name
    power_off_via_v1: Callable[[str], list]       # runs v1.0's real path; returns role records
    say: Callable[[str], None]
    confirm: Callable[[str], str]
    sleep: Callable[[float], None]
    pause: Callable[[str], object] = lambda prompt: None   # used only with --pause


def _by_number(outlets):
    return {int(o["number"]): o for o in outlets}


def _show(say, outlets):
    for outlet in outlets:
        say(f"  outlet {outlet['number']}: {outlet['name']!r:<16} {'ON' if outlet['is_on'] else 'OFF'}")


def list_outlets(env) -> int:
    env.say("Read-only listing of the power strip (nothing is switched):")
    _show(env.say, env.read_outlets())
    return 0


def _validate(outlets, outlet_number, expected_alias, layout=None):
    layout = layout or starfront_layout()
    allowed = layout.allowed_test_outlets()
    if isinstance(outlet_number, bool) or not isinstance(outlet_number, int) \
            or outlet_number not in allowed or outlet_number in layout.protected_numbers:
        if layout.starfront:
            raise OutletTestRefused(f"Only outlet {TEST_OUTLET} may be tested.")
        raise OutletTestRefused(
            f"Outlet {outlet_number} cannot be tested. Outlets Guardian uses are protected; "
            f"spare outlets you may test: {list(allowed) or 'none'}.")
    if not expected_alias or not expected_alias.strip():
        raise OutletTestRefused("An outlet name is required (--expect-alias).")
    if expected_alias in layout.protected_aliases:
        raise OutletTestRefused(f"{expected_alias!r} is a protected outlet name.")
    numbered = _by_number(outlets)
    if outlet_number not in numbered:
        raise OutletTestRefused(f"The strip has no outlet {outlet_number}.")
    actual = numbered[outlet_number]["name"]
    if actual != expected_alias:
        raise OutletTestRefused(
            f"Outlet {outlet_number} is named {actual!r}, not {expected_alias!r}. Nothing was switched.")
    if sum(1 for o in outlets if o["name"] == expected_alias) != 1:
        raise OutletTestRefused(f"More than one outlet is named {expected_alias!r}.")
    if any(numbered[n]["name"] == expected_alias for n in layout.protected_numbers if n in numbered):
        raise OutletTestRefused("That name is also used by a protected outlet.")


def _states(outlets):
    return {int(o["number"]): bool(o["is_on"]) for o in outlets}


def run_test(env, outlet_number, expected_alias, pause=False, layout=None) -> int:
    layout = layout or starfront_layout()
    say = env.say
    say(f"=== Live test of Guardian 1.0's power-off path on outlet {outlet_number} ===")

    try:
        before_outlets = env.read_outlets()
        _validate(before_outlets, outlet_number, expected_alias, layout)
    except OutletTestRefused as exc:
        say(f"REFUSED: {exc}")
        return 1

    say("The strip right now:")
    _show(say, before_outlets)
    say("")
    say(f"This will switch outlet {outlet_number} ({expected_alias!r}) through Guardian 1.0's real shutdown path.")
    say("No other outlet will be commanded. Nothing may be plugged into this outlet.")
    phrase = f"OUTLET {outlet_number} IS EMPTY"
    answer = env.confirm(f"Type {phrase} to continue, anything else cancels: ")
    if answer.strip() != phrase:
        say("Cancelled. Nothing was switched.")
        return 1

    def checkpoint(expected_state):
        if pause:
            say("")
            say(f">>> Look at outlet {outlet_number} ({expected_alias!r}) in the Kasa app now. It should show {expected_state}.")
            say("    (Pull down to refresh the app; it can take a few seconds to catch up.)")
            env.pause("    Press Enter when you have looked (Ctrl-C to stop; the outlet will be put back): ")

    start = _states(before_outlets)
    was_on = start[outlet_number]
    problems = []
    switched_something = False

    try:
        if not was_on:
            say("Outlet is OFF; switching it ON first so the test shows a real change ...")
            env.switch_on(expected_alias)
            switched_something = True
            env.sleep(3)
            if not _by_number(env.read_outlets())[outlet_number]["is_on"]:
                raise RuntimeError("Could not switch the test outlet ON to set up the test.")
            say(f"Confirmed by a fresh read: outlet {outlet_number} is ON.")
        else:
            say(f"Outlet {outlet_number} starts ON.")
        checkpoint("ON")

        say("Running Guardian 1.0's power-off and verification ...")
        switched_something = True
        records = env.power_off_via_v1(expected_alias)
        results = [getattr(r, "result", None) for r in records]
        say(f"  Guardian 1.0 reported: {[getattr(r, 'name', r) for r in results]}")
        if results != [SafetyPowerResult.VERIFIED_OFF]:
            problems.append(f"Guardian 1.0 did not report VERIFIED_OFF (got {results}).")

        env.sleep(3)
        after = env.read_outlets()
        after_states = _states(after)
        if after_states.get(outlet_number) is not False:
            problems.append(f"An independent read shows outlet {outlet_number} is NOT off.")
        else:
            say(f"Confirmed by an independent fresh read: outlet {outlet_number} is OFF.")
        checkpoint("OFF")
        changed = [n for n in sorted(start) if n != outlet_number and after_states.get(n) != start[n]]
        if changed:
            problems.append(f"OTHER outlets changed state during the test: {changed}. "
                            "Stop and check the rig before doing anything else.")
    except Exception as exc:  # report, then still restore below
        problems.append(f"The test could not finish: {exc}")
    finally:
        if switched_something:
            try:
                if was_on:
                    say("Putting the outlet back ON, as it started ...")
                    env.sleep(3)
                    env.switch_on(expected_alias)
                    env.sleep(3)
                    say(f"Outlet {outlet_number} switched back ON.")
                    checkpoint("ON again")
                elif _states(env.read_outlets()).get(outlet_number):
                    say("Putting the outlet back OFF, as it started ...")
                    env.sleep(3)
                    env.power_off_via_v1(expected_alias)
                    env.sleep(3)
                final = env.read_outlets()
                final_states = _states(final)
                wrong = [n for n in sorted(start) if final_states.get(n) != start[n]]
                if wrong:
                    problems.append(f"After restoring, outlets {wrong} are not in their starting state.")
                else:
                    say("Every outlet is back in its starting state.")
            except Exception as exc:
                problems.append(f"RESTORE FAILED: {exc}. Check outlet {outlet_number} in the Kasa app.")

    say("")
    if problems:
        say("RESULT: FAILED")
        for problem in problems:
            say(f"  - {problem}")
        return 1

    say("RESULT: PASSED. Guardian 1.0's real power-off path switched the outlet off, verified it,")
    say("and no other outlet changed.")
    return 0


def v1_power_off(transport, alias, outlet_number=TEST_OUTLET, controller_id=CONTROLLER_ID):
    """Run Guardian 1.0's real shutdown path for the one test outlet only; returns the role records."""
    from modules.kasa_safety_power_adapter import KasaEndpointConfig, KasaSafetyPowerAdapter
    from modules.safety_power import (
        SafetyPowerEndpoint, SafetyPowerEndpointRequirements,
        SafetyPowerResourceEffects, SafetyPowerTopology)
    from modules.safety_power_manager import SafetyPowerManager

    adapter = KasaSafetyPowerAdapter(
        controller_id=controller_id,
        endpoints={ENDPOINT_ID: KasaEndpointConfig(outlet_number, alias)},
        transport=transport)
    endpoint = SafetyPowerEndpoint(controller_id, ENDPOINT_ID)
    topology = SafetyPowerTopology({SafetyPowerRole.ACCESSORIES: endpoint})
    requirements = {endpoint: SafetyPowerEndpointRequirements(endpoint, frozenset())}
    effects = {endpoint: SafetyPowerResourceEffects(endpoint, frozenset())}
    manager = SafetyPowerManager({controller_id: adapter})
    return manager.power_off_roles({SafetyPowerRole.ACCESSORIES}, topology, requirements, effects)


def real_environment(kasa_host, say=print, confirm=input, sleep=None, outlet_number=TEST_OUTLET,
                     layout=None) -> Environment:
    layout = layout or starfront_layout()
    if layout.controller_type == "digital_loggers_rest":
        return real_environment_dli(kasa_host, layout, outlet_number, say=say, confirm=confirm, sleep=sleep)
    import asyncio
    import time

    from modules.kasa_controller import KasaController
    from modules.kasa_safety_power_adapter import PythonKasaTransport

    controller = KasaController(kasa_host)

    def read_outlets():
        return asyncio.run(controller.get_outlets())

    def switch_on(name):
        asyncio.run(controller.set_outlet_power(name, True))

    def power_off_via_v1(alias):
        username, password = controller._credentials()
        transport = PythonKasaTransport(host=kasa_host, username=username, password=password)
        return v1_power_off(transport, alias, outlet_number, layout.controller_id if not layout.starfront else CONTROLLER_ID)

    return Environment(read_outlets=read_outlets, switch_on=switch_on,
                       power_off_via_v1=power_off_via_v1, say=say, confirm=confirm,
                       sleep=sleep or time.sleep, pause=input)


def real_environment_dli(host, layout, outlet_number, say=print, confirm=input, sleep=None, transport=None) -> Environment:
    """Digital Loggers (REST) version. UNTESTED ON REAL HARDWARE; run guardian_v1_dli_probe.py first.
    Switching the empty test outlet back ON uses the transport's test-only method (Guardian itself never switches ON)."""
    import time

    from modules.guardian_v1_dli_transport import DigitalLoggersTransport, dli_credentials

    options = layout.options or {}

    def make():
        if transport is not None:
            return transport
        username, password = dli_credentials()
        return DigitalLoggersTransport(host=host, username=username, password=password,
                                       port=options.get("port"), scheme=options.get("scheme", "http"))

    def read_outlets():
        rows = make().survey(layout.outlet_count)
        bad = [row for row in rows if row[3] is not None or row[2] is None]
        if bad:
            raise RuntimeError("The controller did not give a clear name and state for every outlet: "
                               + "; ".join(f"outlet {r[0]}: {r[3] or 'no state'}" for r in bad))
        return [{"number": n, "name": name, "is_on": state.name == "ON"} for n, name, state, _ in rows]

    def switch_on(name):
        make().power_on_outlet_for_test(outlet_number, name)

    def power_off_via_v1(alias):
        return v1_power_off(make(), alias, outlet_number, layout.controller_id)

    return Environment(read_outlets=read_outlets, switch_on=switch_on, power_off_via_v1=power_off_via_v1,
                       say=say, confirm=confirm, sleep=sleep or time.sleep, pause=input)
