# Patch 8: commissioning rehearsal

`guardian_v1_rehearsal.py` runs the real armed gate, supervisor, recovery logic and
one-connection Kasa shutdown against the REAL strip, with the roof, ASIAIR and UPS
inputs simulated. It produces evidence for the "integrated emergency shutdown"
commissioning check. It never approves commissioning and never powers anything on.

Scenarios: roof-closed (default), asiair-lost, ups-low, internal-fault, restart-while-armed.

Safety: throwaway recovery file (the real one is never touched); refuses if v0.6 is
running, if a live monitor reports ARMED, if the strip address differs from the YAML,
if any outlet is unreadable, or if all targets are already off (unless
--allow-already-off). Outlet 1 (Mac mini) is only ever read; the run FAILS if it changed.
Real runs need `--confirm CUT_OUTLETS_2_3_4` and typing CUT.

Evidence: ~/Library/Application Support/GuardianV1/rehearsals/rehearsal_<scenario>_<time>.json
(schema guardian-rehearsal-v1, commissioning_authorized always false).

    python guardian_v1_rehearsal.py --installation-config config/config.yaml \
        --kasa-host 192.168.1.30 --dry-run
