"""The strip is checked sparingly: one connection, once a minute, three tries."""
from datetime import datetime, timezone

import pytest

from modules.asiair_state import AsiairStateTracker
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    RoofState,
    SafetyPowerRole,
    SafetyPowerState,
)
from modules.guardian_v1_observation_cycle import run_observation_cycle
from modules.kasa_safety_power_adapter import KasaEndpointConfig, KasaSafetyPowerAdapter
from modules.observatory_observation_coordinator import ObservatoryObservationCoordinator
from modules.observatory_safety import ObservatorySafetyObservation
from modules.safety_power import SafetyPowerEndpoint, SafetyPowerTopology
from modules.safety_power_capability_probe import probe_safety_power_control
from modules.safety_power_probe_schedule import SafetyPowerProbeSchedule


class Strip:
    """Batch-capable fake. down=True: the strip answers nothing."""

    def __init__(self):
        self.reads = []
        self.down = False
        self.unreadable = set()

    def get_outlet_states(self, requests):
        self.reads.append(list(requests))
        return {n: (None if self.down or n in self.unreadable else SafetyPowerState.ON)
                for n, _a in requests}

    def power_off_outlets(self, requests):
        return {n: True for n, _a in requests}

    def check_outlet(self, n, alias):
        raise AssertionError("per-outlet check must not be used when batch works")


def adapter(strip):
    return KasaSafetyPowerAdapter(
        controller_id="pier", transport=strip,
        endpoints={"asiair": KasaEndpointConfig(2, "ASIAIR"),
                   "mount": KasaEndpointConfig(3, "Wave 150i")})


TOPOLOGY = SafetyPowerTopology({
    SafetyPowerRole.ASIAIR: SafetyPowerEndpoint("pier", "asiair"),
    SafetyPowerRole.MOUNT: SafetyPowerEndpoint("pier", "mount"),
})


def probe(strip):
    return probe_safety_power_control(topology=TOPOLOGY, adapters={"pier": adapter(strip)})


# --- one connection ----------------------------------------------------------------


def test_probe_reads_both_required_outlets_over_one_connection():
    strip = Strip()
    result = probe(strip)
    assert result.status is CapabilityStatus.AVAILABLE
    assert len(strip.reads) == 1 and {n for n, _ in strip.reads[0]} == {2, 3}


def test_probe_with_an_unreachable_strip_is_unknown_not_available():
    strip = Strip(); strip.down = True
    assert probe(strip).status is CapabilityStatus.UNKNOWN


def test_probe_with_one_unreadable_or_misnamed_outlet_is_unknown():
    strip = Strip(); strip.unreadable = {3}
    assert probe(strip).status is CapabilityStatus.UNKNOWN


def test_probe_still_works_with_a_transport_that_cannot_batch():
    class OldStyle:
        def __init__(self): self.checked = []
        def check_outlet(self, n, alias):
            self.checked.append(n); return True
        def get_outlet_state(self, n, alias): return SafetyPowerState.ON
        def power_off_outlet(self, n, alias): return True
    old = OldStyle()
    assert probe(old).status is CapabilityStatus.AVAILABLE
    assert sorted(old.checked) == [2, 3]


# --- the schedule -------------------------------------------------------------------


class Clock:
    t = 0.0
    def __call__(self): return self.t


def test_first_check_runs_immediately_then_waits_a_minute():
    clock, strip = Clock(), Strip()
    sched = SafetyPowerProbeSchedule(clock=clock)
    assert sched.run(lambda: probe(strip)).status is CapabilityStatus.AVAILABLE
    for t in (5, 30, 59):
        clock.t = t
        assert sched.run(lambda: probe(strip)) is None
    clock.t = 60
    assert sched.run(lambda: probe(strip)) is not None
    assert len(strip.reads) == 2


def test_two_failures_do_not_degrade_but_the_third_does():
    clock, strip = Clock(), Strip()
    sched = SafetyPowerProbeSchedule(clock=clock)
    sched.run(lambda: probe(strip))
    strip.down = True
    clock.t = 60
    assert sched.run(lambda: probe(strip)) is None            # attempt 1 fails: keep last
    clock.t = 65
    assert sched.run(lambda: probe(strip)) is None            # attempt 2 fails: keep last
    clock.t = 70
    assert sched.run(lambda: probe(strip)).status is CapabilityStatus.UNKNOWN  # attempt 3


def test_retries_are_spaced_not_back_to_back():
    clock, strip = Clock(), Strip()
    sched = SafetyPowerProbeSchedule(clock=clock)
    sched.run(lambda: probe(strip))
    strip.down = True
    clock.t = 60
    sched.run(lambda: probe(strip))
    clock.t = 61  # too soon after the failed attempt
    n = len(strip.reads)
    assert sched.run(lambda: probe(strip)) is None
    assert len(strip.reads) == n


def test_a_success_between_failures_resets_the_count():
    clock, strip = Clock(), Strip()
    sched = SafetyPowerProbeSchedule(clock=clock)
    sched.run(lambda: probe(strip))
    for round_start in (60, 130, 200):
        strip.down = True
        clock.t = round_start
        assert sched.run(lambda: probe(strip)) is None
        clock.t = round_start + 5
        assert sched.run(lambda: probe(strip)) is None
        strip.down = False
        clock.t = round_start + 10
        assert sched.run(lambda: probe(strip)).status is CapabilityStatus.AVAILABLE


def test_schedule_validates_settings():
    with pytest.raises(ValueError):
        SafetyPowerProbeSchedule(interval_seconds=0)
    with pytest.raises(ValueError):
        SafetyPowerProbeSchedule(failures_to_degrade=0)


# --- through the real observation cycle ---------------------------------------------


class Roof:
    def observe(self):
        return ObservatorySafetyObservation(state=RoofState.OPEN, observed_at=datetime.now(timezone.utc))


class Ping:
    def is_reachable(self): return True


def cycles(strip, clock, seconds, schedule):
    registry = CapabilityRegistry({
        Capability.ASIAIR_MONITORING, Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL})
    tracker, coordinator = AsiairStateTracker(2), ObservatoryObservationCoordinator()
    history = []
    for t in range(0, seconds, 5):
        clock.t = float(t)
        run_observation_cycle(
            registry=registry, asiair_tracker=tracker, observatory_coordinator=coordinator,
            asiair_adapter=Ping(), observatory_adapter=Roof(), now=datetime.now(timezone.utc),
            roof_max_age_seconds=30, safety_power_topology=TOPOLOGY,
            safety_power_adapters={"pier": adapter(strip)}, safety_power_schedule=schedule)
        history.append((t, registry.status(Capability.SAFETY_POWER_CONTROL)))
    return history


def test_five_minutes_of_five_second_cycles_touch_the_strip_five_times():
    clock, strip = Clock(), Strip()
    cycles(strip, clock, 300, SafetyPowerProbeSchedule(clock=clock))
    assert len(strip.reads) == 5  # t = 0, 60, 120, 180, 240


def test_a_strip_that_dies_is_reported_unknown_only_after_three_tries_about_ten_seconds():
    clock, strip = Clock(), Strip()
    sched = SafetyPowerProbeSchedule(clock=clock)
    # run 60 s healthy, then the strip dies
    healthy = cycles(strip, clock, 60, sched)
    assert all(s is CapabilityStatus.AVAILABLE for _t, s in healthy)
    strip.down = True
    registry = CapabilityRegistry({
        Capability.ASIAIR_MONITORING, Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL})
    registry.update(Capability.SAFETY_POWER_CONTROL, CapabilityStatus.AVAILABLE)
    tracker, coordinator = AsiairStateTracker(2), ObservatoryObservationCoordinator()
    seen = {}
    for t in (60, 65, 70, 75):
        clock.t = float(t)
        run_observation_cycle(
            registry=registry, asiair_tracker=tracker, observatory_coordinator=coordinator,
            asiair_adapter=Ping(), observatory_adapter=Roof(), now=datetime.now(timezone.utc),
            roof_max_age_seconds=30, safety_power_topology=TOPOLOGY,
            safety_power_adapters={"pier": adapter(strip)}, safety_power_schedule=sched)
        seen[t] = registry.status(Capability.SAFETY_POWER_CONTROL)
    assert seen[60] is CapabilityStatus.AVAILABLE
    assert seen[65] is CapabilityStatus.AVAILABLE
    assert seen[70] is CapabilityStatus.UNKNOWN


def test_without_a_schedule_behaviour_is_unchanged_every_cycle_probes():
    clock, strip = Clock(), Strip()
    cycles(strip, clock, 30, None)
    assert len(strip.reads) == 6
