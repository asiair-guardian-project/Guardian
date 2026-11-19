import json
from datetime import datetime, timedelta, timezone

from guardian_v1_watch import main
from modules.guardian_types import RoofState
from modules.guardian_v1_monitoring_watch import run_watch
from modules.observatory_safety import ObservatorySafetyObservation

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return T0 + timedelta(seconds=self.t)

    def sleep(self, s):
        self.t += s

    def mono(self):
        return self.t


class Roof:
    def __init__(self, clock, state=RoofState.OPEN, age=0.0, fail=False):
        self.clock, self.state, self.age, self.fail = clock, state, age, fail

    def observe(self):
        if self.fail:
            raise ConnectionError("roof feed down")
        return ObservatorySafetyObservation(
            state=self.state, observed_at=self.clock.now() - timedelta(seconds=self.age))


class Asiair:
    def __init__(self):
        self.up = True

    def is_reachable(self):
        return self.up


def watch(asiair, roof, clock, seconds=30, **kw):
    return run_watch(asiair_adapter=asiair, observatory_adapter=roof, seconds=seconds,
                     interval_seconds=5, sleep=clock.sleep, clock=clock.mono,
                     now_fn=clock.now, **kw)


def test_normal_readings_are_recorded():
    c = Clock()
    r = watch(Asiair(), Roof(c), c)
    row = r["rows"][-1]
    assert row["asiair_state"] == "ONLINE" and row["roof_state"] == "OPEN"
    assert row["roof_reading_age_seconds"] == 0.0
    assert r["commissioning_authorized"] is False


def test_asiair_dropout_and_recovery_are_seen():
    c, a = Clock(), Asiair()
    orig = c.sleep

    def sleep(s):
        orig(s)
        a.up = not (10 <= c.t < 20)
    r = run_watch(asiair_adapter=a, observatory_adapter=Roof(c), seconds=40,
                  interval_seconds=5, sleep=sleep, clock=c.mono, now_fn=c.now)
    states = [x["asiair_state"] for x in r["changes"]]
    assert states == ["ONLINE", "LOST", "ONLINE"]


def test_failed_roof_feed_reads_unknown_and_capability_unavailable():
    c = Clock()
    r = watch(Asiair(), Roof(c, fail=True), c)
    row = r["rows"][-1]
    assert row["roof_state"] == "UNKNOWN"
    assert row["roof_capability"] != "AVAILABLE"


def test_stale_roof_reading_is_not_trusted():
    c = Clock()
    r = watch(Asiair(), Roof(c, age=600), c)
    assert r["rows"][-1]["roof_state"] == "UNKNOWN"


def test_roof_unknown_times_out_to_closed_after_grace():
    c = Clock()
    r = watch(Asiair(), Roof(c, fail=True), c, seconds=90)
    assert r["rows"][-1]["roof_effective_state"] == "CLOSED"
    assert r["rows"][-1]["roof_unknown_timed_out"] is True


def test_roof_closed_is_reported_closed():
    c = Clock()
    r = watch(Asiair(), Roof(c, state=RoofState.CLOSED), c)
    assert r["rows"][-1]["roof_state"] == "CLOSED"


def test_an_escaping_error_is_recorded_not_hidden(monkeypatch):
    import modules.guardian_v1_monitoring_watch as w
    c = Clock()
    monkeypatch.setattr(w, "run_observation_cycle",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = watch(Asiair(), Roof(c), c, seconds=5)
    assert "RuntimeError" in r["rows"][0]["cycle_error"]


def test_cli_writes_evidence_and_switches_nothing(tmp_path, monkeypatch):
    c = Clock()
    lines = []
    import modules.guardian_v1_monitoring_watch as w
    monkeypatch.setattr(w.time, 'sleep', lambda s: None)
    code = main(["--asiair-host", "x", "--alpaca-host", "y", "--alpaca-port", "1",
                 "--seconds", "0", "--evidence-dir", str(tmp_path)],
                asiair_adapter=Asiair(), observatory_adapter=Roof(c), out=lines.append)
    assert code == 0
    f = list(tmp_path.glob("watch_*.json"))
    assert len(f) == 1 and json.loads(f[0].read_text())["schema"] == "guardian-monitoring-watch-v1"


def test_watch_code_cannot_switch_power():
    from pathlib import Path
    for name in ("modules/guardian_v1_monitoring_watch.py", "guardian_v1_watch.py",
                 "modules/guardian_v1_watch_power.py"):
        text = Path(name).read_text().lower()
        assert "power_off" not in text and "turn_off" not in text
    assert "kasa" not in Path("modules/guardian_v1_monitoring_watch.py").read_text().lower()
    reader = Path("modules/guardian_v1_watch_power.py").read_text()
    assert "get_outlet_states" in reader and "power_off" not in reader


def test_macos_ping_timeout_makes_the_asiair_state_lost_end_to_end(monkeypatch):
    """Regression: on macOS an unanswered ping exits 2; it must read LOST."""
    from types import SimpleNamespace
    from modules.asiair_icmp_adapter import AsiairIcmpAdapter
    from tests.test_asiair_icmp_adapter import MAC_NO_REPLY

    answer = {"up": True}

    def fake_run(*a, **k):
        if answer["up"]:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=2, stdout=MAC_NO_REPLY)

    monkeypatch.setattr("modules.asiair_icmp_adapter.subprocess.run", fake_run)
    c = Clock()
    orig = c.sleep

    def sleep(s):
        orig(s)
        answer["up"] = not (10 <= c.t < 25)
    r = run_watch(asiair_adapter=AsiairIcmpAdapter("192.168.1.20"),
                  observatory_adapter=Roof(c), seconds=40, interval_seconds=5,
                  sleep=sleep, clock=c.mono, now_fn=c.now)
    assert [x["asiair_state"] for x in r["changes"]] == ["ONLINE", "LOST", "ONLINE"]


def test_one_dropped_ping_does_not_make_the_asiair_lost_by_default():
    c, a = Clock(), Asiair()
    orig = c.sleep

    def sleep(s):
        orig(s)
        a.up = not (10 <= c.t < 15)  # exactly one missed check
    r = run_watch(asiair_adapter=a, observatory_adapter=Roof(c), seconds=40,
                  interval_seconds=5, sleep=sleep, clock=c.mono, now_fn=c.now)
    assert [x["asiair_state"] for x in r["changes"]] == ["ONLINE"]


class Strip:
    def __init__(self, c, fail_from=None, unreadable=False):
        self.c, self.fail_from, self.unreadable = c, fail_from, unreadable
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.fail_from is not None and self.c.t >= self.fail_from:
            raise OSError("strip unreachable")
        return {2: object(), 3: None if self.unreadable else object()}


def test_all_three_paths_are_counted_together_when_the_strip_is_read():
    c = Clock()
    r = watch(Asiair(), Roof(c), c, power_reader=Strip(c))
    assert r["power_strip_checked"] is True
    assert r["cycles_with_all_three_paths_available"] == r["cycles"] == 7


def test_a_strip_that_stops_answering_breaks_the_simultaneous_count():
    c = Clock()
    r = watch(Asiair(), Roof(c), c, power_reader=Strip(c, fail_from=15))
    assert 0 < r["cycles_with_all_three_paths_available"] < r["cycles"]
    assert r["rows"][-1]["power_strip_readable"] is False


def test_an_unreadable_outlet_means_the_strip_path_is_not_available():
    c = Clock()
    r = watch(Asiair(), Roof(c), c, power_reader=Strip(c, unreadable=True))
    assert r["cycles_with_all_three_paths_available"] == 0


def test_a_failed_roof_feed_breaks_the_simultaneous_count_even_with_the_strip_fine():
    c = Clock()
    r = watch(Asiair(), Roof(c, fail=True), c, power_reader=Strip(c))
    assert r["cycles_with_all_three_paths_available"] == 0


def test_without_a_strip_reader_no_simultaneous_claim_is_made():
    c = Clock()
    r = watch(Asiair(), Roof(c), c)
    assert r["power_strip_checked"] is False
    assert r["cycles_with_all_three_paths_available"] == 0


def test_cli_with_kasa_host_reports_the_simultaneous_count(tmp_path, monkeypatch):
    import modules.guardian_v1_monitoring_watch as w
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    c = Clock()
    lines = []
    asked = {}

    def factory(host):
        asked["host"] = host
        return Strip(c)

    code = main(["--asiair-host", "x", "--alpaca-host", "y", "--alpaca-port", "1",
                 "--seconds", "0", "--kasa-host", "192.168.1.30",
                 "--evidence-dir", str(tmp_path)],
                asiair_adapter=Asiair(), observatory_adapter=Roof(c),
                out=lines.append, power_reader_factory=factory)
    assert code == 0 and asked["host"] == "192.168.1.30"
    assert any("ALL available together: 1 of 1" in line for line in lines)


# --- baseline run: raw ping summary, checkpoints, early stop -------------------------


def test_summary_counts_single_misses_that_the_two_miss_rule_hides():
    c, a = Clock(), Asiair()
    orig = c.sleep

    def sleep(s):
        orig(s)
        a.up = not (c.t in (10.0, 30.0, 45.0))  # isolated single misses
    r = run_watch(asiair_adapter=a, observatory_adapter=Roof(c), seconds=60,
                  interval_seconds=5, sleep=sleep, clock=c.mono, now_fn=c.now)
    assert [x["asiair_state"] for x in r["changes"]] == ["ONLINE"]  # never LOST
    s = r["asiair_ping_summary"]
    assert s["missed"] == 3 and s["longest_miss_streak"] == 1 and s["errors"] == 0


def test_summary_reports_longest_streak_and_silence_in_seconds():
    c, a = Clock(), Asiair()
    orig = c.sleep

    def sleep(s):
        orig(s)
        a.up = not (10 <= c.t < 25)  # three misses in a row: t=10, 15, 20
    r = run_watch(asiair_adapter=a, observatory_adapter=Roof(c), seconds=60,
                  interval_seconds=5, sleep=sleep, clock=c.mono, now_fn=c.now)
    s = r["asiair_ping_summary"]
    assert s["longest_miss_streak"] == 3 and s["longest_silence_seconds"] == 15.0


def test_a_probe_that_errors_is_counted_as_an_error_not_a_miss():
    class Broken:
        def is_reachable(self):
            raise RuntimeError("ping could not run")
    c = Clock()
    r = watch(Broken(), Roof(c), c, seconds=20)
    s = r["asiair_ping_summary"]
    assert s["errors"] == s["checks"] > 0 and s["missed"] == 0


def test_checkpoints_are_offered_while_running_and_a_failed_save_is_harmless():
    c = Clock()
    seen = []

    def checkpoint(report):
        seen.append((report["cycles"], report["complete"]))
        raise OSError("disk full")
    r = watch(Asiair(), Roof(c), c, seconds=60, on_checkpoint=checkpoint, checkpoint_every=4)
    assert [n for n, _ in seen] == [4, 8, 12] and all(not done for _, done in seen)
    assert r["complete"] is True and r["cycles"] == 13


def test_an_early_stop_request_ends_the_run_cleanly_and_is_marked():
    c = Clock()
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] >= 3
    r = watch(Asiair(), Roof(c), c, seconds=3600, should_stop=stop)
    assert r["interrupted"] is True and r["cycles"] == 3 and r["complete"] is True


def test_cli_saves_one_file_and_prints_the_ping_summary(tmp_path, monkeypatch):
    import modules.guardian_v1_monitoring_watch as w
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    c, lines = Clock(), []
    main(["--asiair-host", "x", "--alpaca-host", "y", "--alpaca-port", "1", "--seconds", "0",
          "--evidence-dir", str(tmp_path)], asiair_adapter=Asiair(),
         observatory_adapter=Roof(c), out=lines.append)
    assert len(list(tmp_path.glob("watch_*.json"))) == 1
    assert not list(tmp_path.glob("*.tmp"))
    assert any(line.startswith("ASIAIR checks: 1, missed: 0, errors: 0") for line in lines)


def test_an_error_after_good_answers_is_not_recorded_as_the_previous_answer():
    class Flaky:
        def __init__(self):
            self.n = 0

        def is_reachable(self):
            self.n += 1
            if self.n == 3:
                raise RuntimeError("ping could not run")
            return True
    c = Clock()
    r = watch(Flaky(), Roof(c), c, seconds=25)
    raw = [row["asiair_ping_raw"] for row in r["rows"]]
    assert raw[:4] == [True, True, None, True]
    assert r["asiair_ping_summary"]["errors"] == 1
