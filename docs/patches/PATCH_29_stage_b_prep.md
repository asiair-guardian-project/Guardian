# Patch 29 - Stage B preparation: switch, rollback, status and the v0.6 start guard

Nothing in this patch changes who protects the rig. v0.6 stays the live protection until the operator runs the switch.

## guardian_stage_b.py   (status | switch | rollback; DRY RUN unless --apply)
    .venv/bin/python guardian_stage_b.py status
    .venv/bin/python guardian_stage_b.py switch            # dry run: checks and plan only
    .venv/bin/python guardian_stage_b.py switch --apply    # asks you to type CUT POWER
    .venv/bin/python guardian_stage_b.py rollback --apply

switch (Stage A -> B): refuses unless v0.6 is DISARMED (or off), v1.0 is running DISARMED and watching only, and the v1.0 launchd file has
everything ARM needs (commissioning record exists, kasa host, installation config, recovery file, socket). Then: back up the v1.0 launchd
file, stop and disable v0.6, add `--enable-hardware-execution YES_CUT_POWER` to the v1.0 launchd file, restart v1.0 (stays DISARMED), wait until
it reports it can cut power. A failed switch restores the old files and the old v0.6 state. It never ARMS; you ARM v1.0 in its app.

rollback (B -> A): refuses while v1.0 is ARMED (restarting an armed v1.0 would cut power; DISARM first). Removes the hardware option, restarts
v1.0 watching only, re-enables and starts v0.6 (comes up DISARMED). It never ARMS.

status: who is protecting. PROTECTED_BY is one of v0.6, v1.0, NONE, CONFLICT (both armed with cutting ability), UNKNOWN.
Neither switch nor rollback ever switches power or touches outlet 1.

## v0.6 start guard
main.py (v0.6) now asks the v1.0 monitor, before starting, whether v1.0 is ARMED with hardware execution enabled; if so v0.6 exits (code 75)
instead of starting, so two supervisors can never both cut power. It FAILS OPEN: any doubt (no socket, v1.0 down, odd reply, any error,
guard module missing) lets v0.6 start exactly as before. Today (v1.0 watching only) it can never block v0.6. It takes effect the next time v0.6 starts.
Under launchd's KeepAlive a blocked v0.6 is retried every ~10 s and logs a line each time; the switch disables v0.6 in launchd anyway.

## imaging_check.sh
Now supervisor-aware: READY when v0.6 is armed (Stage A) or v1.0 is armed with hardware enabled (Stage B); NOT READY for CONFLICT, NONE or unknown.

## Tests
tests/test_guardian_v1_stage_b.py (28) and tests/test_guardian_v1_start_guard.py (15) use a simulated launchd, v0.6 and v1.0.
Mutation-checked 12 ways (each safety rule removed in turn is caught).
Not testable in the build environment: real launchctl, the real v1.0 launcher; the DRY RUN on the Mac is the first real exercise.
