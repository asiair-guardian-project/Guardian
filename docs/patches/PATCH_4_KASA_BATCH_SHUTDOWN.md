# Patch 4: one-connection Kasa emergency shutdown

Connecting to the HS300 takes about 1.35 s (measured on the Starfront strip).
Guardian 1.0 reconnected for every command and every check: 6 connections to
cut and verify 3 outlets (about 8 s or more). Now: 1 connection to command all
three outlets, 1 fresh connection to verify them (about 3 s).

Unchanged safety rules: every outlet is still checked by number AND name
before it is switched; an outlet is VERIFIED_OFF only when a fresh read says
off; one outlet failing never blocks the others; outlet 1 is never a target;
shutdown order is the same; unreachable strip -> FAILED (retried each cycle
as before); switching stays blocked under pytest without the live-hardware
override. A transport without the new methods uses the old one-at-a-time path.

Files: modules/kasa_safety_power_adapter.py, modules/safety_power_manager.py,
tests/test_guardian_v1_kasa_batch_shutdown.py (9 tests).
