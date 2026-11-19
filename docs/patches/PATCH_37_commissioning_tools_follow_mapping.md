# Patch 37: commissioning tools follow the operator's outlet mapping

The outlet live test, the evidence audit and the rehearsal (a real power cut) used the fixed Starfront wiring. They now
read the same `power` section as the monitor, through one shared module, `modules/guardian_v1_layout.py`.

* No `power` section: exactly the Starfront behaviour as before. Pinned by a test: the evidence-audit fingerprint is
  byte-identical to the one the old code produced; the outlet test still only accepts outlet 5; the rehearsal token is
  still `CUT_OUTLETS_2_3_4`.
* With a `power` section (Kasa HS300 or Digital Loggers):
  * `guardian_v1_outlet_test.py list` / `test --outlet N --expect-alias NAME`: any outlet nothing is mapped to may be
    tested (Starfront: only 5). Every mapped outlet and the host computer's outlet are refused by number and by name.
    The layout comes from the installation config named in the live monitor's launchd file. A refused outlet is
    refused before the strip is contacted. Digital Loggers: restoring the empty test outlet uses a test-only ON command
    (`power_on_outlet_for_test`, used by nothing else).
  * `guardian_v1_evidence_audit.py --installation-config FILE`: reports the operator's outlets, host outlet and
    controller type; the fingerprint changes if any of them change.
  * `guardian_v1_rehearsal.py`: cuts only the three mapped outlets (ASIAIR, mount, accessories), checks the host outlet
    is unchanged afterwards, and the typed confirmation is `CUT_OUTLETS_<the three numbers>`; `--dry-run` prints it.
* Wizard next steps point to these tools.

## Not changed
`guardian_v1_phase_b_final_runner.py`, `guardian_v1_phase_b_live_preflight.py` and `guardian_v1_phase_b_dry_run.py` are
the early Starfront-only Phase B scripts (fixed strip address and outlets 1-4). They are superseded by the rehearsal and
are not for other operators.

## Limits
Digital Loggers paths are tested only against the simulated controller (tests/dli_fake.py).
