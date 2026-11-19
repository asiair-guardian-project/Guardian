"""The v1.0 event log: v0.6-style lines, only for changes that matter."""
import os
import re
import time
from datetime import datetime, timedelta

from modules.guardian_types import RoofState
from modules.guardian_v1_event_journal import (
    EventJournal, RigEventObserver, LOG_NAME)
from tests.test_guardian_v1_armed_runtime import (  # noqa: F401
    Asiair, FakeKasa, Roof, Running, ask, build, status, wait_for, workdir)
from tests.test_guardian_v1_armed_launch import env  # noqa: F401

LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[(INFO|WARNING|ERROR|ACTION|CRITICAL)\s*\] "
                  r"[A-Z0-9_]+ \| [A-Z0-9_]+ \| .+$")


def attach(workdir, runner):
    journal = EventJournal(workdir / "logs")
    runner._observer = RigEventObserver(journal)
    return journal


def lines(journal):
    return journal.path.read_text().splitlines() if journal.path.exists() else []


def has(journal, *parts):
    return any(all(p in line for p in parts) for line in lines(journal))


def test_a_protected_night_reads_like_the_v06_log(workdir):
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof)
    journal = attach(workdir, runner)
    with Running(runner):
        ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert wait_for(lambda: status(workdir)["session"] == "IMAGING_PERMITTED")
        time.sleep(0.5)  # many quiet cycles
        roof.state = RoofState.CLOSED
        assert wait_for(lambda: status(workdir)["session"] == "ABORTED")
        time.sleep(0.3)
    out = lines(journal)
    assert all(LINE.match(line) for line in out), out
    assert has(journal, "MONITOR | STARTED")
    assert has(journal, "ROOF | OPEN") and has(journal, "ROOF | CLOSED")
    assert has(journal, "ARM | ARMED") and has(journal, "SESSION | IMAGING_PERMITTED")
    assert has(journal, "[CRITICAL]", "PROTECTION | INCIDENT_OPENED", "ROOF_CLOSED")
    for outlet_action in ("SAFETY_POWER_OFF_ASIAIR", "SAFETY_POWER_OFF_MOUNT",
                          "SAFETY_POWER_OFF_ACCESSORIES"):
        assert has(journal, "POWER |", outlet_action, "VERIFIED_OFF")
    assert has(journal, "MONITOR | STOPPED")
    # Dozens of cycles ran; only changes were written, each exactly once.
    assert len(out) < 25
    assert sum("ROOF | CLOSED" in line for line in out) == 1
    assert sum("ROOF | OPEN" in line for line in out) == 1


def test_when_v06_does_the_cut_v10_just_notes_what_it_sees(workdir):
    class Flaky(Asiair):
        up = True

        def is_reachable(self):
            return self.up
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof)
    air = Flaky()
    runner.observation_runtime._asiair_adapter = air
    journal = attach(workdir, runner)
    with Running(runner):
        time.sleep(0.3)
        roof.state = RoofState.CLOSED
        air.up = False
        assert wait_for(lambda: has(journal, "ROOF | CLOSED"))
        assert wait_for(lambda: has(journal, "ASIAIR | LOST"))
        time.sleep(0.3)
    assert has(journal, "[WARNING ]", "ASIAIR | LOST")
    assert not has(journal, "INCIDENT")
    assert not has(journal, "POWER |")
    assert kasa.commands == []


def test_a_refused_arm_is_logged_with_its_reason_once(workdir):
    app, runner = build(workdir, kasa=FakeKasa(), roof=Roof(), hardware=False)
    journal = attach(workdir, runner)
    with Running(runner):
        ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert wait_for(lambda: has(journal, "ARM | REFUSED"))
        time.sleep(0.3)
    assert has(journal, "ARM | REFUSED", "launch setting")
    assert sum("ARM | REFUSED" in line for line in lines(journal)) == 1
    assert has(journal, "Power cut by this monitor: DISABLED")


class _Obs:
    def __init__(self, roof="OPEN", air="ONLINE", ups=False):
        from types import SimpleNamespace as N
        self.roof_state = N(name=roof)
        self.asiair_state = N(name=air)
        self.ups_low_battery = ups


def test_failed_cycles_are_reported_once_and_recovery_once(workdir, env):
    runner, _l, _ = env.build("--commissioning-record", env.sign_off())
    journal = EventJournal(workdir / "logs")
    obs = RigEventObserver(journal)
    app, gate = runner.application, runner.gate
    for failure in (None, "net down", "net down", "net down", None, None):
        obs.observe(application=app, gate=gate,
                    observation=None if failure else _Obs(), failure=failure)
    assert sum("OBSERVATION_FAILED" in line for line in lines(journal)) == 1
    assert sum("OBSERVATION_RESTORED" in line for line in lines(journal)) == 1


def test_a_journal_problem_never_reaches_the_runtime(workdir, env):
    runner, _l, _ = env.build("--commissioning-record", env.sign_off())
    blocker = workdir / "not_a_dir"
    blocker.write_text("x")
    journal = EventJournal(blocker)  # cannot create a directory here
    assert journal.event("INFO", "A", "B", "c") is False
    obs = RigEventObserver(journal)
    assert obs.observe(application=None, gate=None, observation=None) is None


def test_log_rotates_daily_and_keeps_seven_days(workdir):
    now = [datetime(2026, 11, 3, 21, 0, 0)]
    journal = EventJournal(workdir / "logs", clock=lambda: now[0])
    journal.event("INFO", "ROOF", "OPEN", "Roof status changed to OPEN.")
    old = workdir / "logs" / f"{LOG_NAME}.2026-10-20"
    old.write_text("old\n")
    now[0] += timedelta(days=1)
    journal.event("INFO", "ROOF", "CLOSED", "Roof status changed to CLOSED.")
    assert (workdir / "logs" / f"{LOG_NAME}.2026-11-03").exists()
    assert not old.exists()  # older than 7 days
    assert len(lines(journal)) == 1 and "CLOSED" in lines(journal)[0]


def test_it_is_a_different_file_from_v06s_log(workdir):
    assert EventJournal(workdir / "logs").path.name == "guardian_v1.log"
    assert LOG_NAME != "guardian.log"


def test_the_launcher_wires_the_journal_into_the_project_logs(env):
    runner, _l, _ = env.build("--commissioning-record", env.sign_off())
    assert runner._observer is not None
    assert runner._observer.journal.path == env.root / "logs" / LOG_NAME


def test_a_capability_nothing_ever_sets_does_not_raise_a_false_alarm(workdir):
    """State verification stays UNKNOWN by design; it must not be logged."""
    app, runner = build(workdir, kasa=FakeKasa(), roof=Roof())
    journal = attach(workdir, runner)
    with Running(runner):
        assert wait_for(lambda: has(journal, "SESSION | DISARMED"))
        time.sleep(0.3)
    assert not has(journal, "WARNING")
    assert not has(journal, "STRIP")
