"""UPS-unreadable grace tracker and the optional abort alert. No network."""
from types import SimpleNamespace

import pytest

from modules.abort_alerter import AbortAlerter, AlertLevel
from modules.guardian_types import ProtectionTrigger
from modules.ups_adapter import (
    DEFAULT_UNREADABLE_GRACE_SECONDS,
    UpsReadError,
    UpsReading,
    UpsReadTracker,
    read_ups_low_battery,
)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class Ups:
    def __init__(self, reading=None):
        self.reading = reading or UpsReading(False, 100)
        self.fail = False

    def read(self):
        if self.fail:
            raise UpsReadError("usb dropout")
        return self.reading


def test_default_grace_is_fifteen_minutes():
    assert DEFAULT_UNREADABLE_GRACE_SECONDS == 900


def test_short_unreadable_spell_is_tolerated_then_counts_as_low():
    clock, ups = Clock(), Ups()
    tracker = UpsReadTracker(900, clock=clock)
    ups.fail = True

    assert tracker.low_battery(ups, 35) is False  # clock starts
    clock.advance(899)
    assert tracker.low_battery(ups, 35) is False  # one second short
    clock.advance(1)
    assert tracker.low_battery(ups, 35) is True  # grace used up
    clock.advance(60)
    assert tracker.low_battery(ups, 35) is True  # and stays low


def test_a_good_read_resets_the_clock():
    clock, ups = Clock(), Ups()
    tracker = UpsReadTracker(900, clock=clock)
    ups.fail = True
    tracker.low_battery(ups, 35)
    clock.advance(800)
    ups.fail = False
    assert tracker.low_battery(ups, 35) is False  # recovered
    ups.fail = True
    clock.advance(10)
    assert tracker.low_battery(ups, 35) is False  # new spell starts now
    clock.advance(800)
    assert tracker.low_battery(ups, 35) is False  # 800 s < 900 s since restart


def test_good_reads_still_follow_the_normal_battery_rules():
    tracker = UpsReadTracker(clock=Clock())
    assert tracker.low_battery(Ups(UpsReading(True, 34)), 35) is True
    assert tracker.low_battery(Ups(UpsReading(True, 36)), 35) is False
    assert tracker.low_battery(Ups(UpsReading(False, 1)), 35) is False


def test_no_adapter_is_never_low():
    assert UpsReadTracker(clock=Clock()).low_battery(None, 35) is False


def test_grace_must_be_positive():
    for bad in (0, -5):
        with pytest.raises(ValueError):
            UpsReadTracker(bad)


def test_without_a_tracker_unreadable_still_means_not_low():
    ups = Ups()
    ups.fail = True
    assert read_ups_low_battery(ups, 35) is False  # old behaviour preserved


def test_read_function_delegates_to_the_tracker():
    clock, ups = Clock(), Ups()
    tracker = UpsReadTracker(10, clock=clock)
    ups.fail = True
    read_ups_low_battery(ups, 35, tracker)
    clock.advance(10)
    assert read_ups_low_battery(ups, 35, tracker) is True


# --- abort alerter ------------------------------------------------------------


def incident(unresolved=(), triggers=(ProtectionTrigger.ROOF_CLOSED,)):
    return SimpleNamespace(
        triggers=set(triggers),
        unresolved_actions=[SimpleNamespace(name=n) for n in unresolved],
    )


class Outbox:
    def __init__(self):
        self.sent = []

    def __call__(self, level, message):
        self.sent.append((level, message))


def test_default_level_is_off_and_sends_nothing():
    box = Outbox()
    alerter = AbortAlerter(send=box)
    assert alerter.level is AlertLevel.OFF
    alerter.observe(incident())
    alerter.observe(incident(unresolved=["SAFETY_POWER_OFF_MOUNT"]))
    for _ in range(10):
        alerter.observe(incident(unresolved=["SAFETY_POWER_OFF_MOUNT"]))
    assert box.sent == []


def test_off_with_no_sender_is_safe():
    assert AbortAlerter(level="off", send=None).observe(incident()) == 0


def test_level_parsing():
    assert AlertLevel.parse(None) is AlertLevel.OFF
    assert AlertLevel.parse("ALL") is AlertLevel.ALL
    assert AlertLevel.parse(" Failure ") is AlertLevel.FAILURE
    with pytest.raises(ValueError):
        AlertLevel.parse("sometimes")


def test_all_sends_once_per_abort_even_when_observed_many_times():
    box = Outbox()
    alerter = AbortAlerter("all", box)
    inc = incident()
    for _ in range(5):
        alerter.observe(inc)
    assert len(box.sent) == 1
    assert "ROOF_CLOSED" in box.sent[0][1]


def test_failure_level_stays_quiet_when_power_off_is_verified():
    box = Outbox()
    alerter = AbortAlerter("failure", box)
    inc = incident()
    for _ in range(10):
        alerter.observe(inc)
    assert box.sent == []


def test_failure_alert_waits_for_the_failure_to_persist():
    box = Outbox()
    alerter = AbortAlerter("failure", box, failure_confirm_cycles=3)
    bad = incident(unresolved=["SAFETY_POWER_OFF_MOUNT"])
    alerter.observe(bad)
    alerter.observe(bad)
    assert box.sent == []  # two cycles: could still be a Wi-Fi blip
    alerter.observe(bad)
    assert len(box.sent) == 1
    assert box.sent[0][0] == "CRITICAL"
    assert "SAFETY_POWER_OFF_MOUNT" in box.sent[0][1]
    for _ in range(5):
        alerter.observe(bad)
    assert len(box.sent) == 1  # never repeats for the same abort


def test_a_failure_that_clears_itself_never_alerts():
    box = Outbox()
    alerter = AbortAlerter("failure", box, failure_confirm_cycles=3)
    inc = incident(unresolved=["SAFETY_POWER_OFF_MOUNT"])
    alerter.observe(inc)
    alerter.observe(inc)
    inc.unresolved_actions = []  # the retry worked
    for _ in range(5):
        alerter.observe(inc)
    assert box.sent == []


def test_the_failure_count_must_be_consecutive():
    box = Outbox()
    alerter = AbortAlerter("failure", box, failure_confirm_cycles=3)
    inc = incident(unresolved=["SAFETY_POWER_OFF_ASIAIR"])
    alerter.observe(inc)
    alerter.observe(inc)
    inc.unresolved_actions = []
    alerter.observe(inc)  # resolved for a cycle: count restarts
    inc.unresolved_actions = [SimpleNamespace(name="SAFETY_POWER_OFF_ASIAIR")]
    alerter.observe(inc)
    alerter.observe(inc)
    assert box.sent == []


def test_all_level_sends_abort_then_a_second_alert_if_power_off_fails():
    box = Outbox()
    alerter = AbortAlerter("all", box, failure_confirm_cycles=2)
    bad = incident(
        unresolved=["SAFETY_POWER_OFF_MOUNT"],
        triggers=(ProtectionTrigger.UPS_LOW_BATTERY,),
    )
    alerter.observe(bad)
    alerter.observe(bad)
    assert [level for level, _ in box.sent] == ["WARNING", "CRITICAL"]
    assert "UPS_LOW_BATTERY" in box.sent[0][1]


def test_next_abort_alerts_again_after_the_incident_is_released():
    box = Outbox()
    alerter = AbortAlerter("all", box)
    alerter.observe(incident())
    alerter.observe(None)  # operator released the abort
    alerter.observe(incident())
    assert len(box.sent) == 2


def test_a_broken_sender_never_raises_into_protection():
    def broken(level, message):
        raise OSError("no internet")

    alerter = AbortAlerter("all", broken)
    assert alerter.observe(incident()) == 0  # swallowed, not raised


def test_failure_confirm_cycles_must_be_positive():
    with pytest.raises(ValueError):
        AbortAlerter("all", Outbox(), failure_confirm_cycles=0)
