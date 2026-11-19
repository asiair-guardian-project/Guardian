# Patch 21 - local web page, read-only first version

`python guardian_v1_web.py` then open http://127.0.0.1:8765 in a browser on the same machine.

## What it shows
Monitor contact, session, roof, ASIAIR, mount motion, whether this monitor's power cut is enabled, ARM state and the reason ARM is unavailable, recovery/incident state, the last 40 lines of logs/guardian_v1.log, and the last 7 nights (same text as guardian_v1_nights.py).
If the monitor cannot be reached, or readings go stale, the page says so in red and greys the values. It never shows an old value as current.

## Design
- A SEPARATE program from the monitor. It talks to the monitor's existing operator socket and only ever sends STATUS. If it dies or hangs, protection is unaffected.
- Loopback only: binds 127.0.0.1; there is no option to bind elsewhere.
- Host header must be 127.0.0.1:<port> or localhost:<port> (blocks DNS rebinding).
- GET only. No buttons, forms or inputs: it cannot ARM, DISARM, acknowledge or change anything.
- The incident token, recovery-file path and setup data in the monitor's reply are not passed to the browser.
- Strict Content-Security-Policy, no inline script, all text inserted with textContent.

## Not in this version
Controls (ARM / DISARM / acknowledge) and the setup wizard. Controls need a per-session token plus Origin checks and a decision on remote access; they come next. Windows support and running it as a launchd job also come later.

## Tests
tests/test_guardian_v1_web.py (16). Mutation-checked 6 ways: host check, status whitelist, POST refusal, loopback bind, STATUS-only, CSP.
