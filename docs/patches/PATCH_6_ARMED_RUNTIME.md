# Patch 6: armed-capable runtime and launcher (nothing is installed or armed)

New entry point: `guardian_v1_armed.py`. `guardian_v1.py` (the watch-only
monitor) is NOT modified and still has no way to arm; a test enforces that.

## What it is
* modules/guardian_v1_armed_runtime.py - the loop. Every cycle runs through the
  ARM gate, the operator socket gets the gate (so ARM/DISARM work), and an
  optional abort alerter runs after each cycle.
* modules/guardian_v1_armed_launch.py - builds it, with the safety checks.
* modules/guardian_v1_commissioning_record.py - loads the operator's signed-off
  commissioning record. Fails closed: any problem = empty record = ARM refused.

## Safety rules (each has a test, and each was proven by breaking the code)
1. Hardware execution is OFF unless the launch line has exactly
   `--enable-hardware-execution YES_CUT_POWER`. Even then ARM is a separate,
   deliberate operator action and needs a valid commissioning record.
2. Hardware cannot be enabled while Guardian v0.6 is running (its status file
   shows a live process).
3. The strip address must equal kasa.power_strip_ip in the installation YAML;
   the installation must match the launch settings and have no pending
   activation (same as the watch-only monitor).
4. No / invalid / wrong-configuration / unsafe-permission commissioning record:
   the monitor still starts (watch-only) but ARM is refused.
5. Restart while armed is always on in this launcher (Patch 1): if Guardian
   restarts with an armed session on record it cuts power and latches ABORTED,
   even if the relaunch lacks the hardware token.
6. Only one monitor can own the operator socket, so the watch-only and armed
   monitors cannot run together; swap them deliberately.

## Behaviour to know about
* If an unexpected error escapes a cycle while armed, the gate disarms and
  turns hardware execution off (existing gate behaviour); the runtime logs it,
  counts it (`cycle_errors`) and keeps running. A restart re-enables it.
  Whether such a fault should instead ABORT (cut power) is an open decision.
* Stopping or restarting the armed monitor during an armed session counts as
  "restart while armed" and cuts power on the next launch.

## Examples (text only, not installed)
docs/patches/examples/org.guardian.v1.armed-monitor.plist.example
docs/patches/examples/commissioning-record.example.json (all NOT_TESTED, so
copying it unchanged cannot commission anything)
