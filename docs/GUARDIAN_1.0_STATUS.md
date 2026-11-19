# Guardian 1.0 Development Status

This document records implementation and validation milestones for Guardian
1.0. The normative design specification remains
`GUARDIAN_1.0_ARCHITECTURE.md`.

## Current Status

Guardian 1.0 has a hardware-neutral safety backbone with:

- session-state orchestration;
- required-capability tracking;
- ASIAIR monitoring abstraction;
- observatory safety abstraction;
- generic Safety Power architecture;
- hardware-neutral protection planning and execution;
- independent mount STOP capability support;
- latched ABORTED state;
- unresolved-action retry handling;
- commissioning and readiness models;
- configuration fingerprinting and commissioning audit persistence.

## Required Runtime Capabilities

The current required protection capabilities are:

- ASIAIR monitoring;
- observatory safety monitoring;
- Safety Power control.

Loss of a required capability during established imaging causes the imaging
session to be aborted and invokes the configured protection response.

## Safety Power Architecture

Guardian Core uses logical Safety Power roles and generic endpoints.

Hardware-specific controller behavior is isolated behind Safety Power
Adapters. This permits different installations to use Kasa, Pegasus, EAGLE,
Wanderer, SVBONY, network PDUs, controllable UPS outputs, relay systems, or
other future controller types without changing Guardian Core.

Runtime endpoint checks are non-destructive.

Physical proof that a configured endpoint actually removes power from the
intended equipment belongs to commissioning.

## Kasa Adapter

A Guardian 1.0 Kasa Safety Power adapter and python-kasa transport have been
implemented.

The adapter maps a generic Guardian endpoint ID to a configured physical Kasa
outlet number and expected alias.

Both outlet number and alias must match before the adapter accepts the
endpoint. A mismatched identity prevents switching.

Power command and shutdown verification are separate operations.

The implementation targets python-kasa 0.10.2.

## Live Non-Destructive Kasa Validation

Date: 2026-10-04

Controller:
- Kasa HS300 at the existing observatory installation.

Observed outlet identities:
- Outlet 1: Mac Mini
- Outlet 2: ASIAIR
- Outlet 3: Wave 150i
- Outlet 4: Pegasus
- Outlet 5: spare
- Outlet 6: Plug 6

Outlet 1 is the Guardian host power path and was not targeted for control.

Guardian 1.0 generic endpoint validation was exercised live for:

- `asiair` -> outlet 2 / `ASIAIR`
- `mount` -> outlet 3 / `Wave 150i`

Both endpoint identities validated successfully.

Both endpoints correctly reported their current state as OFF.

This validation was read-only. No ON or OFF command was issued.

## Safety Power Retry Policy

For ROOF_CLOSED and ASIAIR_LOST protection events:

- independent mount STOP is attempted where available;
- configured Safety Power-Off is attempted;
- failed required Safety Power actions remain eligible for retry.

If SAFETY_POWER_CONTROL itself is lost during active imaging:

- the session is aborted;
- independent mount STOP is attempted where available;
- the initial configured Safety Power-Off is still attempted;
- if mount STOP is independently verified, persistent Safety Power retry is
  not required solely to secure the already stationary aborted system;
- without positively verified STOP, failed required Safety Power actions
  remain eligible for retry.

## Test Status

A broad repository regression on 2026-10-04 produced:

- 348 passed;
- 3 legacy/test-environment failures.

The three failures were not Guardian 1.0 regressions.

Subsequent focused Guardian 1.0 Safety Power tests passed after the Kasa
adapter and transport were added.

## Next Development Work

Planned work includes:

- integrate live Safety Power capability probing with configured adapters;
- add deliberate physical commissioning workflow for Safety Power endpoints;
- add additional Safety Power controller adapters as needed;
- implement real mount adapters behind the generic mount interface;
- complete operator-facing commissioning/configuration workflow;
- integrate Guardian 1.0 runtime status and notifications;
- perform end-to-end Guardian 1.0 hardware commissioning.

### Full Runtime Capability Probe Validation

A subsequent live read-only test exercised the complete Guardian 1.0 runtime
Safety Power capability path:

    physical Kasa HS300
        -> PythonKasaTransport
        -> KasaSafetyPowerAdapter
        -> SafetyPowerTopology
        -> probe_safety_power_control()
        -> CapabilityProbeResult

The live result was:

    Capability: SAFETY_POWER_CONTROL
    Status: AVAILABLE
    Observation: True
    Detail: required Safety Power endpoints are available

Both required endpoints were validated non-destructively. No power-switching
command was issued.

This demonstrates that Guardian 1.0 can establish the required Safety Power
runtime capability through the generic adapter architecture using real
controller hardware.

## Live Wave Mount Adapter Validation

Date: 2026-10-04

The Guardian 1.0 WaveMountAdapter was exercised against the installed
Sky-Watcher Wave 150i through Guardian's independent SynScan UDP path.

Read-only motion tests produced:

- powered and idle: STATIONARY
- sidereal tracking: MOVING

A deliberate active STOP test was then performed while the mount was tracking.

Results:

- before STOP: MOVING
- STOP request: SUCCEEDED
- STOP verification: SUCCEEDED
- after STOP: STATIONARY

Guardian independently verified the STOP by comparing motor positions after
the direct STOP command.

After the out-of-band Guardian STOP, the ASIAIR continued to display
Tracking ON / Sidereal even though repeated independent Wave position
sampling showed the mount remained physically STATIONARY.

This demonstrates that the ASIAIR tracking indication may remain logically
stale after an independent Guardian STOP. Guardian therefore uses independent
mount-position verification rather than the ASIAIR tracking indication as
evidence that the mount has stopped.

The ASIAIR did not automatically restart physical mount motion during the
observation interval. Tracking was subsequently turned OFF manually in the
ASIAIR to return the test installation to a consistent normal state.

No HOME, PARK, GOTO, or power-switching command was used during this test.
