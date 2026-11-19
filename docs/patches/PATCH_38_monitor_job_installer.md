# Patch 38: monitor job installer for new operators

New: `guardian_v1_install_monitor.py` (+ `modules/guardian_v1_monitor_job.py`). Builds the launchd file that runs the
v1.0 monitor (`org.guardian.v1.monitor`, `guardian_v1_armed.py`) from the operator's installation config.

    .venv/bin/python guardian_v1_install_monitor.py --config config/config.yaml           # show only
    .venv/bin/python guardian_v1_install_monitor.py --config config/config.yaml --write   # create the file

* WATCHING ONLY: the file never contains `--enable-hardware-execution`; guardian_stage_b.py (explicit go-ahead) is still
  the only way v1.0 gets the ability to cut power. Stage B accepts the generated file and round-trips it.
* Never loads the job, never arms, never contacts a device or switches power. It prints the `launchctl bootstrap`
  command for the operator to run.
* Never overwrites an existing launchd file (O_EXCL). Creates the support folder `~/Library/Application Support/GuardianV1`
  with mode 0700. Refuses relative paths, a bad installation config (same validation as the Setup screen, plus the
  `power` section) and the wizard's `config.guardian-candidate.yaml` (copy it into place as config/config.yaml first, on a
  brand-new install only).
* For the Starfront values it reproduces the live job exactly (pinned by a test using the file printed by plutil on
  2026-11-19, minus the two Stage B hardware arguments). Mutation-checked 8 ways.

Limits: Mac (launchd) only. Does not install Python, the venv or python-kasa.
