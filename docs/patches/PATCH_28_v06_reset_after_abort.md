# Patch 28 - guardian_v06_reset.sh (recovery after a v0.6 abort)

## Why
Found 2026-11-11 after a dew-bounce abort: v0.6 ARM stayed blocked ("requires explicit operator ACK_ABORT").
- Guardian Control's ACKNOWLEDGE ALERT sends ACK (clears the alert only).
- ACK_ABORT cannot succeed: record_emergency_start / record_emergency_abort exist in modules/guardian.py
  but are never called, so guardian_emergency_state.json stays DISARMED ("Persistent record is not ABORTED").
- The Oct 15 durable-emergency-state work added the ACK_ABORT requirement after the Oct 6 log in which an alert ack was enough.
- A v0.6 restart reads the DISARMED record and starts fresh, which is the working recovery.

## What it does
zsh guardian_v06_reset.sh
- REFUSES if v0.6 is running and not DISARMED (or status is unreadable). Nothing is changed.
- If v0.6 is disabled in launchd it prints the enable/bootstrap commands and stops.
- Loads (if not loaded) or restarts (kickstart -k) the v0.6 job, waits up to 40 s for a new PID, prints the result and the roof reading.
- Never cuts or restores power, never ARMs, never edits v0.6 code.

## Not changed
v0.6 code. The real fix (wire the emergency-record calls, add an ACK_ABORT button) is left deliberately; v1.0 has a working ACKNOWLEDGE ABORT flow.
Tested here with stand-ins for launchctl and guardianctl (armed -> refused, disabled -> instructions, disarmed -> restart); the real run is on the Mac.
