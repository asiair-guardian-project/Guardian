# Patch 34 - operator-defined outlet mapping (Kasa HS300)

## Why
Guardian 1.0 could cut power only for the fixed Starfront layout (ASIAIR outlet 2, Wave 150i outlet 3, Pegasus outlet 4; never
outlet 1). Another operator, with another strip layout, could not use it.

## What it adds
An optional `power` section in the installation configuration:

    power:
      type: kasa_hs300
      host_outlet: {number: 1, alias: "Mac Mini"}     # the computer running Guardian: never switched
      targets:
        asiair:      {number: 2, alias: "ASIAIR"}
        mount:       {number: 3, alias: "Wave 150i"}
        accessories: {number: 4, alias: "Pegasus"}

* Without a `power` section nothing changes: the fixed Starfront wiring (guardian_v1_starfront_kasa.py, untouched) is used.
* With one, the monitor wires those outlets instead (modules/guardian_v1_mapped_kasa.py): same adapter, same routing, same
  per-outlet name check before every power-off, same one-connection batch calls, same shutdown order (ASIAIR, then mount,
  then accessories, whatever the outlet numbers).
* Validation (modules/guardian_v1_power_mapping.py): all three targets and the host outlet are required; numbers are whole
  numbers 1 to 6 and all different; names are exact text and all different (case-insensitive); the host outlet can never be
  a target. A present but invalid section stops the monitor starting (nothing is guessed).
* A second guard sits in front of the strip: whatever the mapping says, the transport refuses to switch the host's outlet
  (by number or by name), including inside batch calls.
* The mapping is part of the configuration identity, so changing it means commissioning must be redone.
* The setup wizard (Patch 33) gets an Outlets screen that writes this section, validated by the same rules.

## Limits (deliberate, for now)
* Kasa HS300 only. Digital Loggers is the next step and plugs into the same adapter interface.
* One outlet per role and all three roles required; a rig with fewer or more outlets to cut needs a later change, because
  commissioning has a check per role.
* The Mac app's Setup screen still cannot edit the mapping (changing it needs recommissioning).
* The outlet live test (Patch 30), the evidence audit and the rehearsal scripts are still Starfront-layout specific.
* Outlet names are typed by the operator; confirming them against the strip needs the Kasa sign-in and is a later step.

## Tests
tests/test_guardian_v1_power_mapping.py (41): validation (every unsafe or malformed section refused), the host guard
(number, name, batch, mirroring of batch calls), identical behaviour to the fixed wiring (same commands, order and
connections, with and without batch calls, for several role sets), a renamed outlet refused, a mapping that bypassed
validation still cannot switch the host outlet, startup refusal for an invalid section, and a full simulated night on a layout
unlike Starfront's (only the mapped outlets cut; spares and the host untouched). Mutation-checked 14 ways. The wizard tests
cover the new screen, including a real-Chrome run. While building it a first version silently dropped the batch calls (one
connection per outlet) and cut in a different order; the equivalence tests exist because of that and now pin both.
