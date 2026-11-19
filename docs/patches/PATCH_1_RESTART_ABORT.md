# Patch 1 — Restart-while-armed abort

## What it does
If Guardian stops and starts again while an **armed** session is on record,
it powers off the ASIAIR, mount and accessories (batched, verified, retried
every cycle until confirmed OFF), latches the session ABORTED, and waits for
the operator to acknowledge and release it. Roof state is not consulted:
armed + restart = abort. The incident is stored with trigger
`RESTART_WHILE_ARMED`, so the existing login notice and operator window show it.

## Off by default
`GuardianV1Application(..., allow_restart_abort=False)` is the default, and the
supervisor default is unchanged. The deployed watch-only monitor behaves exactly
as before (a restart after an interrupted session is still a recovery block the
operator inspects). An armed-capable launcher must pass `allow_restart_abort=True`
and a real safety-power executor.

## Files
Changed: `modules/guardian_types.py`, `modules/runtime_supervisor.py`,
`modules/guardian_v1_application.py`
New: `tests/test_guardian_v1_restart_abort.py` (19 tests)

## Things to know
- `DISARM` does not currently end an imaging session in v1.0 (the state stays
  IMAGING_PERMITTED until something aborts it), so a restart after a DISARM that
  was never followed by an abort will also abort. That is existing behaviour of
  the session model, not new.
- The abort runs on the first monitoring cycle after restart, so it waits for
  that cycle's observations (a few seconds).
- Hardware execution is switched on inside the process only for this abort and
  retries, and is switched back off once the operator has released the incident.
- If a restart abort is pending and no safety-power executor was supplied, the
  application raises RuntimeError instead of quietly simulating.
- launchd `KeepAlive` is a separate, manual change to the monitor's plist (not in
  this zip). Without it a crashed monitor is not relaunched.

## Undo
Restore the backup tarball made before applying, or `git checkout -- modules tests`
and delete `tests/test_guardian_v1_restart_abort.py`.
