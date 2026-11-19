# Patch 15: emergency pacing, matched to v0.6

Both rules come from v0.6's code and from the strip's dislike of closely spaced connections.

1. **Read-back pause.** After the OFF command, the verification read waits until 5 s have passed
   since the command's connection closed (v0.6 does the same). The OFF command itself is never
   delayed, and nothing else waits. The incident is marked resolved about 5 s later than before.
2. **Paced retries.** An unresolved shutdown is retried every 15 s for the first 2 minutes, every
   60 s until 12 minutes, then every 300 s (v0.6's schedule). The first cut is immediate. An
   incident restored after a restart retries immediately. Pacing state is never saved.

Tests: `tests/conftest.py` makes retries always due and removes the pause for the older logic
tests; `tests/test_guardian_v1_emergency_pacing.py` tests the pacing itself.
