import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from modules.guardian_v1_night_summary import night_of, read_events, render, summarize

ROOT = Path(__file__).resolve().parent.parent


def line(ts, level, cat, code, msg="x"):
    return f"{ts} [{level:<8}] {cat} | {code} | {msg}\n"


LAST_NIGHT = "".join([
    line("2026-11-03 19:12:52", "INFO", "ROOF", "OPEN"),
    line("2026-11-04 01:09:43", "INFO", "ROOF", "CLOSED"),
    line("2026-11-04 01:11:46", "INFO", "ROOF", "OPEN"),
    line("2026-11-04 04:38:06", "INFO", "ROOF", "CLOSED"),
    line("2026-11-04 04:48:09", "INFO", "ROOF", "OPEN"),
    line("2026-11-04 05:27:10", "INFO", "ROOF", "CLOSED"),
    line("2026-11-04 07:59:02", "WARNING", "ASIAIR", "LOST"),
])


def run(tmp_path, text, name="guardian_v1.log"):
    (tmp_path / name).write_text(text)
    return summarize(read_events(tmp_path))


def test_last_nights_real_events_summarize_correctly(tmp_path):
    nights = run(tmp_path, LAST_NIGHT)
    night = nights[date(2026, 11, 3)]
    assert len(night["closures"]) == 3
    text = render(nights)
    assert "3 roof closure(s), 2 reopened within 30 min" in text
    assert "closed 01:09:43 - reopened 01:11:46  (2 min)" in text
    assert "closed 04:38:06 - reopened 04:48:09  (10 min)" in text
    assert "closed 05:27:10 - still closed at end of log" in text
    assert "ASIAIR lost at 07:59:02" in text


def test_a_restart_that_repeats_the_state_is_not_a_new_closure(tmp_path):
    text = (line("2026-11-04 01:00:00", "INFO", "ROOF", "CLOSED")
            + line("2026-11-04 01:05:00", "INFO", "MONITOR", "STOPPED")
            + line("2026-11-04 01:05:10", "INFO", "MONITOR", "STARTED")
            + line("2026-11-04 01:05:12", "INFO", "ROOF", "CLOSED"))
    night = run(tmp_path, text)[date(2026, 11, 3)]
    assert len(night["closures"]) == 1 and night["gaps"] == []


def test_a_closure_first_seen_right_after_a_start_has_an_unknown_start(tmp_path):
    text = (line("2026-11-04 01:00:00", "INFO", "ROOF", "OPEN")
            + line("2026-11-04 01:10:00", "INFO", "MONITOR", "STOPPED")
            + line("2026-11-04 01:20:00", "INFO", "MONITOR", "STARTED")
            + line("2026-11-04 01:20:02", "INFO", "ROOF", "CLOSED"))
    nights = run(tmp_path, text)
    out = render(nights)
    assert "0 roof closure(s)" in out
    assert "true start unknown" in out
    assert "monitor was NOT running 01:10:00 - 01:20:00" in out


def test_nights_run_noon_to_noon():
    assert night_of(datetime(2026, 11, 4, 11, 59, 59)) == date(2026, 11, 3)
    assert night_of(datetime(2026, 11, 4, 12, 0, 0)) == date(2026, 11, 4)


def test_archives_are_read_in_time_order_and_bad_lines_are_skipped(tmp_path):
    (tmp_path / "guardian_v1.log.2026-11-03").write_text(
        line("2026-11-03 22:00:00", "INFO", "ROOF", "CLOSED") + "garbage line\n")
    (tmp_path / "guardian_v1.log").write_text(
        line("2026-11-04 00:30:00", "INFO", "ROOF", "OPEN")
        + "2026-13-45 99:99:99 [INFO    ] ROOF | OPEN | bad date\n")
    night = summarize(read_events(tmp_path))[date(2026, 11, 3)]
    assert len(night["closures"]) == 1
    assert night["closures"][0]["end"] == datetime(2026, 11, 4, 0, 30, 0)


def test_incidents_are_listed(tmp_path):
    text = line("2026-11-04 02:00:00", "CRITICAL", "PROTECTION", "INCIDENT_OPENED")
    assert "PROTECTION INCIDENT at 02:00:00" in render(run(tmp_path, text))


def test_empty_or_missing_logs_say_so(tmp_path):
    assert render(summarize(read_events(tmp_path))) == "No Guardian v1.0 events found."
    assert render(summarize(read_events(tmp_path / "nope"))) == "No Guardian v1.0 events found."


def test_the_cli_prints_and_changes_nothing(tmp_path):
    (tmp_path / "guardian_v1.log").write_text(LAST_NIGHT)
    before = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    result = subprocess.run([sys.executable, str(ROOT / "guardian_v1_nights.py"),
                             "--log-dir", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0 and "Night of 2026-11-03" in result.stdout
    assert {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == before


def test_only_the_most_recent_nights_are_shown(tmp_path):
    text = "".join(line(f"2026-11-{d:02d} 22:00:00", "INFO", "ROOF", c)
                    for d, c in ((1, "CLOSED"), (2, "OPEN"), (3, "CLOSED")))
    out = render(summarize(read_events(tmp_path := _w(tmp_path, text))), last=1)
    assert "Night of 2026-11-03" in out and "Night of 2026-11-01" not in out


def _w(tmp_path, text):
    (tmp_path / "guardian_v1.log").write_text(text)
    return tmp_path


def test_feed_outages_are_listed_with_their_length(tmp_path):
    text = (line("2026-11-07 08:56:04", "WARNING", "ROOF_FEED", "UNKNOWN")
            + line("2026-11-07 08:57:00", "INFO", "ROOF_FEED", "AVAILABLE")
            + line("2026-11-07 22:00:00", "WARNING", "ROOF_FEED", "UNAVAILABLE")
            + line("2026-11-07 22:03:00", "INFO", "ROOF_FEED", "AVAILABLE")
            + line("2026-11-07 23:00:00", "WARNING", "STRIP", "UNAVAILABLE"))
    out = render(run(tmp_path, text))
    assert "roof feed down 08:56:04 - 08:57:00  (56 s)" in out
    assert "<-" not in out.split("22:00:00")[0]          # 56 s is within the grace
    assert "roof feed down 22:00:00 - 22:03:00  (3 min)  <- longer than the 60 s grace" in out
    assert "power strip down from 23:00:00 - still down at end of log" in out


def test_a_repeated_down_status_does_not_restart_an_outage(tmp_path):
    text = (line("2026-11-07 08:00:00", "WARNING", "ROOF_FEED", "UNKNOWN")
            + line("2026-11-07 08:00:30", "WARNING", "ROOF_FEED", "FAILED")
            + line("2026-11-07 08:02:00", "INFO", "ROOF_FEED", "AVAILABLE"))
    out = render(run(tmp_path, text))
    assert "roof feed down 08:00:00 - 08:02:00" in out and out.count("roof feed down") == 1


def test_the_old_false_strip_verification_warning_is_not_an_outage(tmp_path):
    text = (line("2026-11-03 12:33:50", "WARNING", "STRIP", "UNKNOWN",
                 "Power strip state verification is UNKNOWN.")
            + line("2026-11-03 19:23:22", "WARNING", "STRIP", "UNKNOWN",
                   "Power strip safety-power control is UNKNOWN.")
            + line("2026-11-03 19:25:09", "INFO", "STRIP", "AVAILABLE",
                   "Power strip safety-power control is AVAILABLE."))
    out = render(run(tmp_path, text))
    assert "power strip down 19:23:22 - 19:25:09  (107 s)" in out
    assert "12:33:50" not in out
