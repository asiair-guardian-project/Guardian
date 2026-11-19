# Patch 39: outlet-name check and Keychain credentials helper

* `guardian_v1_check_outlets.py --config FILE` (+ `modules/guardian_v1_outlet_check.py`): READ-ONLY. Reads the power
  controller once (Kasa HS300 or Digital Loggers, per the config's `power.type`; Starfront wiring when there is no
  `power` section) and compares each mapped role and the host computer's outlet with the controller's own names. Exact,
  case-sensitive match required, and the name must be unique on the controller. Exit code 0 only if everything matches.
  Reuses the outlet test's read path; sends no switching command (a test greps the code for any).
* `guardian_v1_credentials.py set kasa|dli` / `check kasa|dli` (+ `modules/guardian_v1_credentials.py`): stores the
  sign-in in the macOS Keychain under the same item names Guardian already reads (account `guardian`: "Guardian Kasa
  Username/Password", "Guardian Digital Loggers Username/Password"; a test ties these to the readers). The user name is
  passed to `security`; the password is NEVER handled by Guardian: `security` prompts for it on the terminal (hidden,
  asked twice). `check` only asks whether the items exist and never requests a secret (-w).
* The setup wizard's next steps now mention both tools, and the monitor job installer (Patch 38).

Tested against simulated controllers and a fake `security`; the real Keychain prompt cannot be exercised in automated
tests (try `check` first: it is harmless). Mutation-checked 6 ways.
