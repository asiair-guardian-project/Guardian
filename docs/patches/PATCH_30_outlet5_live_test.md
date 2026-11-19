# Patch 30 - live test of Guardian 1.0's power-off path on spare outlet 5

Purpose: before Stage B, prove that v1.0's own shutdown code really switches an outlet off and verifies it on the real strip,
without going near the ASIAIR, mount, Pegasus or Mac mini. Until now v1.0 had only been exercised read-only on the live strip (Oct 4).

    .venv/bin/python guardian_v1_outlet_test.py list                                  # read-only: names and states
    .venv/bin/python guardian_v1_outlet_test.py test --expect-alias "<name of outlet 5>"

What `test` does: reads the strip; refuses unless outlet 5 carries exactly the name you gave, the name is unique, and it is not a protected name;
asks you to type OUTLET 5 IS EMPTY; (if the outlet is OFF, switches it ON first using the v0.6 Kasa controller so the test shows a real change);
runs v1.0's real path (SafetyPowerManager -> Kasa adapter -> python-kasa transport, the batch path an emergency uses) for outlet 5 ONLY;
requires v1.0 to report VERIFIED_OFF AND an independent read to show OFF; checks no other outlet changed; puts outlet 5 back as it started.
Only outlet 5 can be selected (the command line rejects any other number; the code also refuses 1-4 by number and by name).
Outlet 1 is additionally refused by the existing v0.6 Kasa controller used for switching back ON.

Patch 30b: `--pause` stops after each switch (ON, OFF, and ON again if it started ON) and asks you to look at outlet 5 in the Kasa app,
a second, independent program reading the strip, with human-paced timing between switches. Ctrl-C at any pause still puts the outlet back.
Also fixed: if the outlet started OFF and the test stopped after switching it ON, it is now switched back OFF (through v1.0's own path).
The test now prints "Confirmed by a fresh read: outlet 5 is ON" / "...independent fresh read: outlet 5 is OFF".

Notes: the v1.0 monitor probes the strip about once a minute; a probe that collides with the test may log a brief STRIP blip while disarmed. Harmless.
Tests: tests/test_guardian_v1_outlet_test.py (33) against a simulated strip using the real manager and adapter; mutation-checked 8 ways.
Not testable in the build environment: the real strip (first real use is on the Mac).
