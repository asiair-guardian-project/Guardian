# Patch 17 - v1.0 refuses ARM while v0.6 is running, and says why

## What changed
- `GuardianV1ArmedGate` takes `arm_blockers`: callables that return None, or a sentence saying why ARM must be refused. A blocker that raises refuses ARM (fail closed).
- `refusal_reason()` is a pure check, in order: already armed; monitor-only launch; open incident; recovery blocked; session not DISARMED; commissioning invalid; blockers. `arm()` uses it and records `last_refusal`.
- The launcher adds one blocker: "Guardian v0.6 is running; stop it before arming v1.0" (reads v0.6's status file plus a pid check).
- STATUS now carries `arm_available` and `arm_unavailable_reason`; the ARM_BLOCKED reply says "ARM refused: <reason>".
- The v1.0 app shows "ARM unavailable: <reason>" in orange.

## Not covered
The check happens at ARM time only. If v0.6 is started after v1.0 is armed, nothing stops it.

## Tests
tests/test_guardian_v1_arm_guard.py (8). Mutation-checked: launcher blocker removed, blockers ignored, and blocker errors swallowed each fail tests.
