# Patch 22 - feed outages in the nightly summary; events page reaches into archives

1. guardian_v1_nights.py (and the web page's "Recent nights") now list each outage of the roof feed, the ASIAIR check and the power strip, with start, end and length. A roof-feed outage of 60 s or more is flagged, because the roof filter treats a feed that is down that long as CLOSED (grace_seconds=60). A feed still down at the end of the log is shown as such.
2. The web page's "Recent events" used to read only today's log file, so it looked nearly empty after each midnight rotation. It now reaches back into the daily archives to fill the last 40 lines.

Tests added to tests/test_guardian_v1_night_summary.py and tests/test_guardian_v1_web.py; mutation-checked (grace flag removed, flag on everything, outage ignoring the feed category, no archive reach).
