# Patch 5: unreadable-UPS limit and optional abort alert

## UPS unreadable for 15 minutes -> abort
Before: an unreadable UPS was always treated as "not low" (same as v0.6), so a
dead USB link silently switched off the power-failure protection.
Now: single bad reads are still ignored, but if the UPS stays unreadable for
15 continuous minutes (default, `ups_unreadable_grace_seconds`), Guardian
treats it as low and aborts like any low-battery. Any good read resets the
clock. Mains failure still leaves 30-45 minutes of UPS, so 15 minutes of
blindness leaves margin to cut the Kasa outlets while the Mac mini (outlet 1)
stays on and restarts itself when power returns.
Wired through: UpsReadTracker (modules/ups_adapter.py) -> run_observation_cycle
-> GuardianV1ShadowRuntime -> both Starfront compose functions.

## Optional phone alert (modules/abort_alerter.py) - OFF by default
Operator setting: off | failure | all.
  failure: only if power-off is still not verified after 3 consecutive cycles
           (a one-cycle Wi-Fi blip that the retry fixes sends nothing).
  all:     every abort, plus a second alert if power-off then fails.
One alert per abort per kind; a broken sender can never affect protection.
The sender is supplied by the caller (e.g. the existing Pushover sender).
NOT YET ATTACHED to a running process: it is wired in when the armed launcher
is built. An incident restored from disk after a restart counts as new, so at
level "all" one alert can repeat after a restart.

Files: modules/ups_adapter.py, modules/abort_alerter.py (new),
modules/guardian_v1_observation_cycle.py, modules/guardian_v1_shadow_runtime.py,
modules/guardian_v1_starfront_kasa_integration.py,
modules/guardian_v1_starfront_composition.py,
tests/test_guardian_v1_ups_grace_and_alert.py (new, 15 tests),
tests/test_guardian_v1_ups_trigger.py (+2 tests).
