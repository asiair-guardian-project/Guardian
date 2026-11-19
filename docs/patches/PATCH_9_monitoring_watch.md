# Patch 9: read-only monitoring watch

`guardian_v1_watch.py` samples the REAL ASIAIR (ping) and REAL roof feed (Alpaca) through
Guardian's own observation cycle and records what Guardian would conclude each cycle.
No power control, no session, no hardware; the code contains no Kasa access.

Evidence (commissioning_authorized always false):
~/Library/Application Support/GuardianV1/watches/watch_<label>_<time>.json
