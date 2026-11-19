# Patch 19 - event log: remove a false STRIP warning

The v1.0 event log (Patch 18) warned "STRIP | UNKNOWN | Power strip state verification is UNKNOWN" at every start.
That capability is never set by any probe and nothing depends on it, so it is always UNKNOWN by design.
It is no longer journaled. Real strip trouble is still logged through the safety-power-control capability.
Test added; mutation-checked (putting it back fails the test).
