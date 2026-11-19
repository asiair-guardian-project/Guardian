# Patch 24 - nightly summary ignores the old false strip warning

Before Patch 19 the event log wrote "STRIP | UNKNOWN | Power strip state verification is UNKNOWN." at every monitor start. Those lines are still in the log, and the summary read one as the start of a real strip outage (showing a 6.9 h outage on Nov 3 that never happened). The summary now ignores any feed line about "state verification". Display only; no effect on protection.
Test: tests/test_guardian_v1_night_summary.py::test_the_old_false_strip_verification_warning_is_not_an_outage (mutation-checked).
