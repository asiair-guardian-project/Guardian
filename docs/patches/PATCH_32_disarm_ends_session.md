# Patch 32 - DISARM ends an established session

## What was wrong (found in the Patch 31 rehearsal, 2026-11-14)
Once a session reached IMAGING_PERMITTED, the session logic ignored the armed flag, and DISARM only cleared that flag. So after DISARM:
* the session stayed IMAGING_PERMITTED and ARM was refused ("Session is IMAGING_PERMITTED, not DISARMED"), with every button greyed out;
* protection kept running although nothing was armed;
* the recovery file kept saying "imaging permitted, not shut down cleanly", so a monitor restart afterwards came up with
  a recovery block ("Guardian restart requires operator recovery").
The only ways out were an abort or a restart. This was already the case before Patch 31.

## The fix
DISARM now also ends an established session: `RuntimeSupervisor.end_session()` returns IMAGING_PERMITTED to DISARMED.
* Saved to the recovery file before it takes effect (a failed save leaves the session unchanged, blocks ARM, and DISARM still revokes ARM).
* Refuses whenever an incident is open: an abort stays latched and is released only by ACKNOWLEDGE ABORT then ALLOW NEW SESSION.
* Never switches power and never ARMS. Earlier states (waiting for roof/protection) already follow the armed flag.
* The ARM-authorization flag is revoked first and unconditionally; nothing after it can leave Guardian armed.
* The operator-socket reply says "session ended (DISARMED)" when a session was ended.

## Behaviour change to know about (decided by the operator, 2026-11-14: "the purpose of disarm is to make the rig available again to the operator")
After DISARM nothing is armed, so a roof closure or lost ASIAIR no longer cuts power until you ARM again. That is what DISARM means;
it is also now the clean way to stop before restarting or switching versions.

## Tests
tests/test_guardian_v1_disarm_session.py (11): re-ARM after DISARM, restart after DISARM is clean, no power change, closing roof after DISARM does not
cut, open incident untouched, failed save, application without end_session, unit rules, socket message. Mutation-checked 6 ways.

The old rule "DISARM does not end an active session; only an abort does" (tests/test_guardian_v1_internal_fault_abort.py) was deliberately reversed;
that test now states the new rule: a fault after DISARM does not cut. A fault while ARMED still cuts, as before.
