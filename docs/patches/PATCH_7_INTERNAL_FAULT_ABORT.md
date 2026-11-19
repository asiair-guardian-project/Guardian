# Patch 7: a Guardian fault while armed cuts power (fail safe)

Operator decision: if Guardian itself malfunctions during an armed night,
protect the gear first and investigate afterwards.

## Behaviour
If an unexpected exception escapes a cycle while Guardian is ARMED or a session
is active (IMAGING_PERMITTED):
1. the rig is powered off (ASIAIR, mount, accessories, one-connection path);
2. the session latches ABORTED with trigger INTERNAL_FAULT and is saved to
   the recovery file;
3. hardware execution stays enabled, so unresolved power-offs keep retrying,
   including on later cycles that fail again (the fault may be what stops the
   normal cycles that do the retrying);
4. the original error is still raised and logged; the armed runtime counts it
   (`cycle_errors`) and keeps running; the abort alerter reports it.
The operator releases it the usual way: acknowledge, then authorize a new
session. ARM stays refused until then. A restart restores the incident and
does not cut again.

## What does NOT cut power
* a fault when nothing is armed and no session is active (no protection was
  being provided; existing behaviour: hardware execution is switched off);
* any fault in a watch-only process or with hardware execution off (nothing
  could be cut, and no unverifiable incident is invented).
Network/adapter failures are not faults: probes turn them into 'unavailable'
statuses before this point (roof outages keep their 60 s grace).

Files: modules/guardian_types.py (INTERNAL_FAULT), runtime_supervisor.py,
guardian_v1_application.py, guardian_v1_armed_gate.py,
tests/test_guardian_v1_internal_fault_abort.py (14 tests).
