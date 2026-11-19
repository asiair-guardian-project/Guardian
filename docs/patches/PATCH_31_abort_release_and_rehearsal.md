# Patch 31 - releasing an acknowledged abort (ALLOW NEW SESSION) and a simulated rehearsal rig

## The gap this closes (found 2026-11-14 with a simulated night)
v1.0 could cut power on a closed roof and let the operator ACKNOWLEDGE the abort, but nothing in the running program could release the
acknowledged incident: `authorize_new_session()` was only called by tests and an acceptance script, the operator socket had no command for it,
and a restart reloads the incident from the recovery file (still latched, acknowledged, recovery blocked). After the first real abort ARM would
have stayed blocked with no operator path out.

## What it adds
* Operator command `RELEASE_ABORT` (same fields as ACKNOWLEDGE_ABORT: command, incident_id, confirmed). Requires the current incident token,
  an acknowledged abort, no unresolved power-off actions and no recovery block; saves durably before taking effect. Result: the session returns to
  DISARMED. It never ARMS, never switches power, never touches hardware. `AUTHORIZE_NEW_SESSION` and everything else stay UNSUPPORTED.
* `RuntimeSupervisor.release_blocker()` / `GuardianV1Application.release_blocker()`: read-only reason release would be refused; a test asserts
  it never disagrees with `authorize_new_session()`.
* STATUS gains `release_available` and `release_unavailable_reason`.
* ARM refusal wording now distinguishes: not acknowledged / acknowledged, release it (ALLOW NEW SESSION) / acknowledged but cannot be released: why.
  ARM is refused in all three, exactly as before.
* Guardian 1.0 app: an ALLOW NEW SESSION button (enabled only when release is available) with a confirmation dialog, status text, and a
  GUARDIAN_V1_SOCKET environment override with a purple REHEARSAL banner so the real app can be pointed at a simulated rig. Rebuild the app with build_on_mac.sh.
* The live monitor needs no action now: it picks the new code up at its next restart (the Stage B switch restarts it).

## Rehearsal rig
    .venv/bin/python guardian_v1_sim_night.py
Runs the REAL v1.0 runtime, gate, supervisor, recovery file and operator socket against a fully simulated roof, ASIAIR, UPS and power strip in a
throw-away folder under /tmp (own socket, own recovery file, own logs). Nothing real is contacted or touched. Roof/ASIAIR are controlled by
writing OPEN/CLOSED/FEED_DOWN to roof.txt and ONLINE/OFFLINE to asiair.txt; strip.txt shows the simulated outlets.

## Tests
tests/test_guardian_v1_abort_release.py (17): command and refusals, durability and failed-save behaviour, status, wording, a full simulated night
(arm, roof closes, cut, acknowledge, release, re-arm), restart persistence, real-socket round trip. Mutation-checked 6 ways.
Not testable in the build environment: the Swift app (no compiler); first compile is on the Mac.
