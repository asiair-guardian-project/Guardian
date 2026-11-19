# Patch 18 - Guardian v1.0 event log (v0.6 style)

## What it does
The armed-capable monitor now writes `logs/guardian_v1.log` in the same line style as v0.6:

    2026-11-03 21:14:09 [CRITICAL] PROTECTION | INCIDENT_OPENED | Protection incident opened. Triggers: ROOF_CLOSED.

Only changes that affect the rig are logged, never one line per check:
- monitor started / stopped (and whether this monitor's power cut is enabled)
- roof OPEN / CLOSED / UNKNOWN, ASIAIR ONLINE / LOST / UNKNOWN, UPS low battery
- roof feed, ASIAIR check and strip capability going down or coming back
- session state changes, ARM granted / revoked, ARM refused (with the reason)
- recovery blocked / cleared
- protection incident opened (with triggers), each power-off result per action (CRITICAL if not verified), incident cleared
- observation or cycle failures, once when they start and once when they recover

Separate file from v0.6's `guardian.log`, so two programs never write one file. Daily rotation, 7 days kept, like v0.6.
Journaling failures are swallowed: they can never stop protection.

## Note
When v1.0 is disarmed (watching only) and v0.6 cuts power, v1.0 logs the roof and ASIAIR changes it sees, and nothing else.

## Tests
tests/test_guardian_v1_event_journal.py (8), mutation-checked 5 ways.
