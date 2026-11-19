# Patch 40: Stage B on a Mac without Guardian 0.6, and the operator guide

* Stage B (`guardian_stage_b.py`) required a Guardian 0.6 launchd file (it refused `switch` and `rollback` without one),
  so a new operator, who never ran 0.6, could not enable cutting at all. Found while writing the operator guide.
  Now: no 0.6 launchd file means no 0.6 on this Mac, so `switch` leaves 0.6 alone (the plan says so) and `rollback`
  only returns v1.0 to watching-only and says plainly that nothing is then protecting the rig. A 0.6 that is RUNNING
  without a launchd file still blocks both (stop it yourself first). With 0.6 present the behaviour is unchanged
  (pinned by tests, including switch then rollback). Mutation-checked 5 ways.
* `docs/OPERATOR_GUIDE.md`: what Guardian will and will not do, requirements, the nine setup steps (wizard, sign-in,
  outlet-name check, monitor job, watching nights, commissioning, app build, Stage B, first supervised night), what to do
  after a cut, and the known limits (the full new-operator path has not been run on a clean second machine; Digital
  Loggers is untested on real hardware; early Phase B scripts are for the original set-up).
