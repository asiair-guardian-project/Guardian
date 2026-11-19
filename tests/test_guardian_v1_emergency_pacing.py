"""Pacing of an emergency: retries match v0.6, and the read-back waits 5 s.

The HS300 strip does not tolerate closely spaced connections, so a cut that
failed to verify is retried every 15 s for 2 minutes, every minute until 12
minutes, then every 5 minutes; and a cut is read back only after a 5 s pause.
The OFF command itself is never delayed.
"""
import pytest

import modules.protection_coordinator as coordinator
from modules.guardian_types import RoofState
from modules.guardian_v1_incident_codec import decode_incident, encode_incident
from modules.protection_coordinator import retry_interval_seconds
from modules.runtime_supervisor import RuntimeSupervisor
from tests.test_runtime_supervisor import (
    POWER_SHUTDOWN, cycle, recording_protection_executor)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(coordinator, "_now", c)  # overrides the test-wide default
    return c


def open_incident(clock):
    supervisor = RuntimeSupervisor()
    attempts = []
    execute = recording_protection_executor(attempts)  # power-off never verifies
    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=execute)
    cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=execute)
    return supervisor, attempts, execute


# --- the schedule ----------------------------------------------------------------


@pytest.mark.parametrize("elapsed,expected", [
    (0, 15), (119.9, 15), (120, 60), (719.9, 60), (720, 300), (86400, 300)])
def test_retry_schedule_matches_v06(elapsed, expected):
    assert retry_interval_seconds(elapsed) == expected


# --- through the supervisor -------------------------------------------------------


def test_cycles_every_five_seconds_do_not_retry_every_cycle(clock):
    supervisor, attempts, execute = open_incident(clock)
    attempts.clear()
    retried_at = []
    for t in range(5, 61, 5):
        clock.t = float(t)
        before = len(attempts)
        cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=execute)
        if len(attempts) > before:
            retried_at.append(t)
    assert retried_at == [15, 30, 45, 60]


def test_a_skipped_cycle_calls_no_executor_at_all(clock):
    supervisor, attempts, execute = open_incident(clock)
    attempts.clear()
    clock.t = 5.0
    result = cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=execute)
    assert attempts == []
    assert result.incident.unresolved_actions == POWER_SHUTDOWN  # still unresolved, still latched


def test_the_first_cut_is_never_paced(clock):
    clock.t = 1000.0  # however late in the process's life the trigger comes
    supervisor, attempts, execute = open_incident(clock)
    assert POWER_SHUTDOWN == attempts[-3:]


def test_backoff_lengthens_after_two_minutes_then_twelve(clock):
    supervisor, attempts, execute = open_incident(clock)
    times = []
    t = 0.0
    while t < 1900:
        t += 5
        clock.t = t
        before = len(attempts)
        cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=execute)
        if len(attempts) > before:
            times.append(t)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert times[:7] == [15, 30, 45, 60, 75, 90, 105]  # every 15 s for 2 minutes
    assert gaps[:6] == [15] * 6 and gaps[6] == 60       # then every minute
    assert 60 in gaps and gaps[-1] == 300               # finally every 5 minutes
    assert max(gaps) == 300 and min(gaps) == 15


def test_an_incident_restored_after_restart_retries_immediately(clock):
    supervisor, attempts, execute = open_incident(clock)
    restored = decode_incident(encode_incident(supervisor.incident))
    assert restored.retry_due() is True
    seen = []
    restored.retry_unresolved(lambda a: seen.append(a) or recording_protection_executor([])(a))
    assert seen  # retried at once, not after waiting out a fresh 15 s


def test_a_verified_incident_is_not_retried_regardless_of_time(clock):
    supervisor = RuntimeSupervisor()
    from modules.guardian_types import SafetyPowerResult
    ok = lambda action: SafetyPowerResult.VERIFIED_OFF
    cycle(supervisor, roof_state=RoofState.OPEN, execute_action=ok)
    cycle(supervisor, roof_state=RoofState.CLOSED, execute_action=ok)
    seen = []
    clock.t = 10_000.0
    cycle(supervisor, roof_state=RoofState.CLOSED,
          execute_action=lambda a: seen.append(a) or ok(a))
    assert seen == []
    assert supervisor.incident.unresolved_actions == []


# --- the read-back pause on the real transport -------------------------------------


def make_transport(monkeypatch, gap=5.0):
    import modules.kasa_safety_power_adapter as module
    from tests.test_guardian_v1_kasa_batch_shutdown import FakeWorld, install
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    world = install(monkeypatch, FakeWorld())
    clock, sleeps = Clock(), []

    def sleep(seconds):
        sleeps.append(round(seconds, 3))
        clock.t += seconds

    transport = module.PythonKasaTransport(
        host="x.invalid", username="u", password="p",
        verify_gap_seconds=gap, clock=clock, sleep=sleep)
    return transport, clock, sleeps, world


REQS = [(2, "ASIAIR"), (3, "Wave 150i"), (4, "Pegasus")]


def test_the_off_command_never_waits_even_right_after_a_read(monkeypatch):
    transport, clock, sleeps, world = make_transport(monkeypatch)
    transport.get_outlet_states(REQS)
    transport.power_off_outlets(REQS)
    assert sleeps == []
    assert sorted(n for _, n in world.log) == [2, 3, 4]


def test_the_read_back_after_a_cut_waits_the_full_gap(monkeypatch):
    transport, clock, sleeps, world = make_transport(monkeypatch)
    transport.power_off_outlets(REQS)
    transport.get_outlet_states(REQS)
    assert sleeps == [5.0]


def test_the_wait_counts_time_already_elapsed(monkeypatch):
    transport, clock, sleeps, world = make_transport(monkeypatch)
    transport.power_off_outlets(REQS)
    clock.t += 3.0
    transport.get_outlet_states(REQS)
    assert sleeps == [2.0]
    transport.power_off_outlets(REQS)
    clock.t += 9.0
    transport.get_outlet_states(REQS)
    assert sleeps == [2.0]  # already more than 5 s: no wait


def test_only_the_first_read_after_a_cut_waits(monkeypatch):
    transport, clock, sleeps, world = make_transport(monkeypatch)
    transport.power_off_outlets(REQS)
    transport.get_outlet_states(REQS)
    transport.get_outlet_states(REQS)
    assert sleeps == [5.0]


def test_a_failed_command_still_paces_the_next_read(monkeypatch):
    import modules.kasa_safety_power_adapter as module
    from tests.test_guardian_v1_kasa_batch_shutdown import FakeWorld, install
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    world = install(monkeypatch, FakeWorld(connects_fail=True))
    clock, sleeps = Clock(), []
    transport = module.PythonKasaTransport(
        host="x.invalid", username="u", password="p", verify_gap_seconds=5.0,
        clock=clock, sleep=lambda s: sleeps.append(s))
    transport.power_off_outlets(REQS)
    transport.get_outlet_states(REQS)
    assert sleeps == [5.0]


def test_production_default_matches_v06_and_negative_gap_is_rejected():
    import modules.kasa_safety_power_adapter as module
    assert module.VERIFY_GAP_SECONDS_V06 == 5.0
    with pytest.raises(ValueError):
        module.PythonKasaTransport(host="x", username="u", password="p",
                                   verify_gap_seconds=-1)


def test_a_transport_built_without_a_gap_uses_the_module_default(monkeypatch):
    import modules.kasa_safety_power_adapter as module
    monkeypatch.setattr(module, "DEFAULT_VERIFY_GAP_SECONDS", 7.5)
    t = module.PythonKasaTransport(host="x", username="u", password="p")
    assert t._verify_gap_seconds == 7.5
