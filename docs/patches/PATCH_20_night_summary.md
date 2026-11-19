# Patch 20 - per-night summary of the v1.0 event log

`python guardian_v1_nights.py [--nights 7] [--log-dir DIR]` reads logs/guardian_v1.log (and its daily archives) and prints, per night (noon to noon, local time, labelled by the evening's date):
- roof closures with start, reopen time and duration, and how many reopened within 30 minutes
- closures already in progress when the monitor (re)started, shown as "true start unknown" and not counted
- ASIAIR losses and protection incidents
- any time the monitor was not running for 2 minutes or more (events in a gap are not recorded)

Read-only: it writes nothing and touches no hardware.
Tests: tests/test_guardian_v1_night_summary.py (9), mutation-checked 4 ways; includes last night's real events.
