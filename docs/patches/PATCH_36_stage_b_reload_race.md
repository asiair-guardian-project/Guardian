# Patch 36: Stage B launchd reload race

On 2026-11-18 `guardian_stage_b.py switch --apply` stopped v0.6, then failed to reload v1.0 with
"Bootstrap failed: 5: Input/output error" (launchd was still unloading v1.0), and its own restore hit the same error.
A manual `launchctl bootstrap` a minute later worked. Nothing was armed and no power was switched.

Fixes (modules/guardian_v1_stage_b.py):
- After `bootout`, wait until launchd no longer lists v1.0, pause 3 s, then `bootstrap` with up to 6 attempts.
- `rollback` now loads v1.0 (watching only) if its file is already watching-only but v1.0 is not running (the old
  code said "already watching only" and left it unloaded).
- The rewritten launchd file keeps the existing file's permissions.
