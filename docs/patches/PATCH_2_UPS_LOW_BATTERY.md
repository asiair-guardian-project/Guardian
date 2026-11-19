# Patch 2 — UPS low-battery abort (apply AFTER Patch 1)

## What it does
Adds `UPS_LOW_BATTERY` as a protection trigger. During an active
(IMAGING_PERMITTED) session, if the UPS is running on battery and its charge is
at or below the threshold (default 35%, as in v0.6), Guardian powers off ASIAIR,
mount and accessories and latches ABORTED, same as a roof closure.

## Policy
- On mains power: never low, whatever the percentage.
- On battery, percentage known: low when `percent <= threshold`.
- On battery, percentage unreadable: low.
- UPS cannot be read at all (pmset error, USB dropout): NOT low (same as v0.6).
- No UPS adapter supplied: feature is off.

## Generic
`modules/ups_adapter.py` reads `pmset -g batt` and does not look for a specific
UPS model (the v0.6 reader only recognised one model).

## Off by default
Nothing reads the UPS unless a launcher passes
`ups_adapter=PmsetUpsAdapter()` (and optionally `ups_low_battery_percent=`) to
`compose_starfront_kasa_integration` or `compose_starfront_read_only`. The
deployed watch-only monitor does not, so it is unchanged.

## Files
New: `modules/ups_adapter.py`, `tests/test_guardian_v1_ups_trigger.py` (35 tests)
Changed (small, default-off additions): `guardian_types.py`, `protection_evaluator.py`,
`session_orchestrator.py`, `guardian_runtime.py`, `runtime_supervisor.py`,
`guardian_v1_application.py`, `guardian_v1_observation.py`,
`guardian_v1_observation_cycle.py`, `guardian_v1_shadow_runtime.py`,
`guardian_v1_starfront_composition.py`, `guardian_v1_starfront_kasa_integration.py`

## Things to know
- The cycle that moves a session into IMAGING_PERMITTED evaluates no triggers
  (existing behaviour), so a UPS already low at arming is acted on one cycle later.
- The UPS trigger applies during an active session only, like the other triggers.

## Undo
Restore the backup tarball made before applying, or `git checkout -- modules tests`
and delete `modules/ups_adapter.py` and `tests/test_guardian_v1_ups_trigger.py`.
