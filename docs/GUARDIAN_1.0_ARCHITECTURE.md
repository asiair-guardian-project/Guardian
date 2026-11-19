# Guardian 1.0 Architecture

## 1. Purpose

Guardian is an independent safety supervisor for unattended and remote
astrophotography systems controlled by ZWO ASIAIR.

Guardian is not an imaging sequencer and does not replace ASIAIR.

Its purpose is to supervise the imaging system from an independent computer
and take protective action when ASIAIR alone can no longer be relied upon to
leave the system in a safe state.

Guardian is particularly intended for installations at remote observatories
where roof or facility safety information is available independently of ASIAIR.

---

## 2. Design Principles

### 2.1 Independent supervision

Guardian must run on a computer independent of ASIAIR.

Loss or malfunction of ASIAIR must not disable Guardian's ability to:

- detect a safety condition;
- determine mount state where supported;
- stop the mount where supported;
- remove power from configured equipment;
- record the event;
- notify the operator.

### 2.2 ASIAIR-oriented design

ASIAIR is a fixed part of the Guardian architecture.

Guardian therefore does not require a generic imaging-controller abstraction
for unrelated imaging platforms.

### 2.3 Hardware-independent safety core

The Guardian safety engine must not contain device-specific assumptions such
as:

- Wave 150i;
- SynScan;
- Kasa;
- Starfront;
- specific IP addresses;
- specific outlet numbers.

Device-specific behavior belongs in adapters.

### 2.4 Defense in depth

Guardian should use independent protection paths where available.

A failure of one control path must not prevent Guardian from attempting other
configured safety actions.

For example:

    ASIAIR -> mount control

may fail while:

    Guardian computer -> mount independent control

and:

    Guardian computer -> network power controller -> mount power

remain available.

### 2.5 Fail-safe uncertainty

Guardian must distinguish:

    SAFE / UNSAFE / UNKNOWN

and:

    MOVING / STATIONARY / UNKNOWN / UNAVAILABLE

UNKNOWN must never silently be treated as a confirmed safe state.

UNAVAILABLE means a capability is intentionally not provided by the
commissioned installation. It is not equivalent to UNKNOWN or FAILED.

The appropriate response to UNKNOWN depends on the safety context and policy.

### 2.6 Safety logic is not user-scriptable

Users may configure their equipment and installation, but the fundamental
Guardian safety rules must not be casually editable through the user
interface.

Configuration describes the installation.

Guardian code determines the safety response.

---

## 3. High-Level Architecture

Guardian consists of six major components:

    Guardian Core
        |
        +-- ASIAIR Monitor
        |
        +-- Observatory Safety Adapter
        |
        +-- Mount Adapter
        |
        +-- Power Adapter
        |
        +-- Operator Services

The Guardian Core owns the session state and safety decisions.

Adapters translate installation-specific hardware and services into
standard Guardian states and actions.

---

## 3.1 Authoritative Safety Model

Guardian recognizes three classes of events that can require protection:

1. The observatory roof closes while ASIAIR remains active.
2. An established ASIAIR connection is lost while the roof remains open.
3. A required commissioned protection capability is lost during an active
   imaging session.

The authoritative top-level decision table is:

| Roof State | ASIAIR State | Guardian Response |
|---|---|---|
| OPEN | ONLINE | Normal operation |
| OPEN | LOST after established connection | Emergency protection |
| CLOSED | OFFLINE | No action; system is already in a safe shutdown condition |
| CLOSED | ONLINE | Shutdown imaging system |

A roof closure while ASIAIR remains online always requires shutdown.

Guardian does not need to determine whether the closure occurred unexpectedly
during imaging or at the normal end-of-night roof-closing time. If the roof is
closed, imaging should no longer be underway.

If ASIAIR is already offline before the roof closes, Guardian takes no
emergency action.

Loss of an established ASIAIR connection while the roof remains open is an
emergency condition because Guardian can no longer rely on ASIAIR to control
or safely terminate the imaging system.

Mount state is not a primary emergency trigger.

Independent mount information improves Guardian's response:

    MOVING:
        attempt controlled STOP, then independent power shutdown

    STATIONARY:
        independent power shutdown when shutdown is required

    UNKNOWN:
        attempt controlled STOP where supported, then independent power shutdown

Failure or absence of independent mount control must never prevent the
independent power shutdown from being attempted.

### Required protection capabilities

Guardian may enter ARMED operation only when it has:

- an authoritative observatory roof/safety source;
- independent monitoring of ASIAIR availability;
- an independent means of removing power from ASIAIR and the mount.

The Safety Power Control path must not depend on ASIAIR.

### Enhanced protection capabilities

The following capabilities improve protection but are not required for
Guardian to operate:

- independent mount communication;
- independent mount motion detection;
- independent controlled mount STOP;
- mount STOP verification;
- independent mount position information.

An installation without independent mount control can still provide valid
Guardian protection through independent Safety Power-Off.

Guardian must clearly report which protection capabilities are available.

---

## 3.2 Supported Deployment Model

Guardian 1.0 intentionally supports a defined class of ASIAIR installations.

Guardian is not intended to accommodate every possible remote-access or
networking arrangement.

Safety and reliability take priority over universal compatibility.

### Guardian Host

Guardian runs on an independent computer located at the observatory.

Supported host platforms may include:

    macOS
    Windows
    Linux

The Guardian host remains operational independently of ASIAIR.

The operator may reach the Guardian host through:

- remote desktop;
- VPN;
- SSH;
- other remote-access systems.

Remote operator access is not part of Guardian's required safety path.

Loss of Internet access, VPN access, or the operator's remote connection must
not remove Guardian's local ability to monitor ASIAIR and execute emergency
power shutdown.

### ASIAIR Network Topology

Guardian supports ASIAIR connected directly to the observatory network.

For example:

    Guardian host
         |
    Observatory LAN
         |
       ASIAIR

Guardian also supports ASIAIR operating on its own local Wi-Fi or hotspot
network.

For example:

                         ASIAIR
                           |
                         Wi-Fi
                           |
    Observatory LAN -- Guardian host
          |
          +-- Safety Power Control
          |
          +-- roof/safety source

In this configuration the Guardian host must maintain simultaneous access to
the ASIAIR network and the observatory safety/control network.

Guardian must not depend on dynamically switching between networks during an
emergency.

### Operator Control of ASIAIR

Guardian does not depend on how the operator normally controls ASIAIR.

The operator may use:

- ASIAIR application on the Guardian host;
- another observatory computer;
- phone;
- tablet;
- remote desktop;
- VPN;
- other supported ASIAIR access methods.

Guardian's concern is its own independent ability to determine ASIAIR
reachability.

### Local Safety Power Requirement

Guardian must have locally available independent Safety Power Control for:

    ASIAIR
    MOUNT

The emergency shutdown path must remain usable without ASIAIR.

The emergency shutdown path must not require the operator's home computer,
remote desktop session, or VPN connection.

A simple UPS or uncontrolled power connection does not satisfy this
requirement.

### Roof / Safety Source Location

The authoritative roof or safety source may be:

- local to the observatory network;
- available through a network share;
- provided by a local API;
- provided through an Internet-accessed observatory service.

If a remote roof/safety service becomes unreachable, Guardian applies the
UNKNOWN-state policy defined elsewhere in this architecture.

Internet loss alone is not interpreted as physical roof closure.

### Simultaneous Safety-Path Availability

During normal Guardian operation, the Guardian host must simultaneously be
able to access:

    ASIAIR
    Safety Power Controller(s)
    configured roof/safety source

Guardian must not rely on disconnecting from one required network in order to
join another required network during a safety event.

Commissioning must verify simultaneous access to the required protection
paths.

### Internet Independence

Guardian's local emergency shutdown capability must not depend on Internet
connectivity.

Internet connectivity may be required for:

- operator remote access;
- notifications;
- an observatory-hosted roof/safety source;
- optional external services.

Loss of those services may reduce monitoring or notification capability but
must not prevent Guardian from executing locally available Safety Power Control
shutdown.

### UPS

UPS protection for the Guardian host, network equipment, and Safety Power Control
control path is strongly recommended but is not a universal Guardian 1.0
requirement.

Where UPS monitoring is available, Guardian may support additional power
states and protective behavior.

UPS monitoring is an enhanced capability and does not replace Guardian's
protection-trigger model:

    authoritative roof closure
    loss of an established ASIAIR connection while the roof is open
    loss of a required commissioned protection capability during imaging

### Unsupported Deployment Example

Guardian 1.0 does not support an architecture in which Guardian runs only on a
remote home computer and depends on an Internet or VPN connection to reach all
observatory safety hardware.

Guardian is intended to continue local protection even when the operator can
no longer reach the observatory.

### Design Principle

Guardian is designed to fail safely, not to operate with every possible
ASIAIR installation.

If the required independent protection paths are unavailable, Guardian must
not enter normal ARMED operation.

---

## 4. Guardian Core

The Guardian Core is responsible for:

- session state;
- protection state;
- safety evaluation;
- event processing;
- emergency action sequencing;
- retry behavior;
- verification;
- alert generation;
- status publication.

The core must not directly communicate with observatory hardware.

---

## 5. Session States

Guardian defines the following session states:

    DISARMED
    WAITING_FOR_ROOF
    WAITING_FOR_PROTECTION
    IMAGING_PERMITTED
    ABORTED

### 5.1 DISARMED

DISARMED means Guardian is monitoring but is not supervising an active
imaging session and will not execute an imaging-session protection response.

### 5.2 WAITING_FOR_ROOF

WAITING_FOR_ROOF means Guardian is ARMED, but the observatory has not yet
provided a confirmed OPEN state.

Typical conditions include:

    ROOF = CLOSED

or:

    ROOF = UNKNOWN

Neither CLOSED nor UNKNOWN may permit imaging.

The ASIAIR may be NOT_ESTABLISHED or ONLINE while Guardian waits for the
roof.

### 5.3 WAITING_FOR_PROTECTION

WAITING_FOR_PROTECTION means Guardian is ARMED and the observatory may be
OPEN, but one or more required commissioned protection capabilities are not
currently READY.

Guardian must not enter IMAGING_PERMITTED while a required protection
capability is unavailable.

Loss of a required capability before imaging begins is therefore a readiness
failure, not an emergency event.

### 5.4 IMAGING_PERMITTED

IMAGING_PERMITTED means:

    Guardian is ARMED;
    the observatory state is confirmed OPEN;
    ASIAIR has been established ONLINE;
    all required commissioned protection capabilities are READY.

Guardian is actively supervising the imaging session.

Once IMAGING_PERMITTED has been entered, loss of a required protection
capability is evaluated as a protection-capability-loss event rather than
merely returning the session to a waiting state.

### 5.5 ABORTED

ABORTED means Guardian has determined that the imaging session must not
continue and has executed or attempted a protection response.

ABORTED is latched until operator action.

ABORTED does not imply that every required protection action succeeded.

Unresolved required protection actions remain active in the emergency retry
engine after the session enters ABORTED.

### 5.6 State Principle

Before imaging:

    missing prerequisite
        -> WAITING state
        -> imaging not permitted

During established imaging:

    protection trigger
        -> protection response
        -> ABORTED

Guardian must never silently downgrade an active protected imaging session
to a waiting state in order to avoid responding to a protection trigger.

---

## 6. ASIAIR Monitor

Guardian monitors ASIAIR availability independently of ASIAIR itself.

The ASIAIR monitor answers one fundamental question:

    Can Guardian independently establish that the configured ASIAIR
    is reachable?

### 6.1 Reachability Methods

The method used to determine reachability is configurable.

The initial Guardian 1.0 implementation may support:

    ICMP / ping

Additional reachability methods may be added later without changing the
Guardian Core safety logic.

A reachability adapter reports:

    ONLINE
    OFFLINE

ONLINE means Guardian received the expected response using the configured
reachability method within its defined timeout.

OFFLINE means the configured reachability test failed.

A single reachability test does not by itself determine whether an emergency
has occurred. Guardian interprets the result in the context of the current
armed session and roof state.

### 6.2 Session Connection State

Guardian maintains a session-aware ASIAIR connection state:

    NOT_ESTABLISHED
    ONLINE
    LOST

NOT_ESTABLISHED means Guardian has been armed, but the configured ASIAIR has
not yet been successfully observed online during the current armed session.

This is a normal startup condition.

It permits Guardian to be armed before ASIAIR is powered on without falsely
declaring a controller-loss emergency.

ONLINE means Guardian has successfully observed the configured ASIAIR online
during the current armed session.

Once ONLINE has been established, Guardian remembers that fact for the
remainder of that armed session.

LOST means:

    1. ASIAIR was previously established ONLINE during the current armed
       session; and

    2. the configured ASIAIR reachability test subsequently reports OFFLINE.

The important transition is therefore:

    NOT_ESTABLISHED -> ONLINE -> LOST

An ASIAIR that has never reached ONLINE during the current armed session
cannot enter LOST merely because it is currently unreachable.

### 6.3 Safety Interpretation

ASIAIR connection state is interpreted together with roof state.

    ROOF OPEN + NOT_ESTABLISHED
        Normal startup / waiting condition.

    ROOF OPEN + ONLINE
        Normal operation.

    ROOF OPEN + LOST
        Emergency protection trigger.

    ROOF CLOSED + NOT_ESTABLISHED
        No emergency action.

    ROOF CLOSED + ONLINE
        Shutdown required.

    ROOF CLOSED + LOST
        No additional roof-triggered shutdown is required if Guardian has
        already initiated the controller-loss protection response.

### 6.4 Session Reset

Starting a new armed session resets the ASIAIR session connection state to:

    NOT_ESTABLISHED

Connection history from a previous session must not cause a controller-loss
event in a new session.

### 6.5 Design Constraint

Guardian must never infer that the mount has stopped merely because ASIAIR
has become unreachable.

ASIAIR reachability and mount motion are separate facts.

## 7. Observatory Safety Adapter

Guardian requires an authoritative observatory roof or safety source that is
independent of ASIAIR.

Guardian does not independently determine whether weather conditions are safe
for observing.

Weather interpretation, roof automation, and decisions such as closure for
rain, wind, humidity, or other facility conditions remain the responsibility
of the observatory.

Guardian consumes the resulting authoritative roof/safety state.

### 7.1 Standard Roof States

Every observatory adapter must translate its source into:

    OPEN
    CLOSED
    UNKNOWN

OPEN means the observatory has positively reported that the roof is open and
imaging may be permitted.

CLOSED means the observatory has positively reported that the roof is closed
or that the facility state requires Guardian to treat the roof as closed.

UNKNOWN means Guardian cannot currently obtain a trustworthy authoritative
roof state.

### 7.2 Source Translation

Different observatories may expose safety information differently.

Possible sources include:

- Alpaca SafetyMonitor;
- network/shared status file;
- HTTP or HTTPS endpoint;
- observatory-specific API.

The adapter is responsible for translating the source into Guardian's
standard OPEN / CLOSED / UNKNOWN states.

For example, an observatory may define:

    SafetyMonitor isSafe = true  -> OPEN
    SafetyMonitor isSafe = false -> CLOSED
    communication failure        -> UNKNOWN

The mapping must be explicitly defined and tested during commissioning.

### 7.3 Freshness

Where a source can become stale, the adapter must evaluate freshness.

Stale data must not be reported as a current authoritative OPEN state.

If Guardian cannot establish that the reported state is current, the adapter
reports:

    UNKNOWN

### 7.4 UNKNOWN Before Imaging Permission

Guardian must never use UNKNOWN to permit imaging.

While the session is:

    WAITING_FOR_ROOF

only a positively confirmed and sufficiently fresh OPEN state may transition
the session to:

    IMAGING_PERMITTED

Therefore:

    OPEN    -> imaging may be permitted
    CLOSED  -> continue waiting
    UNKNOWN -> continue waiting

### 7.5 UNKNOWN During an Established Imaging Session

Once Guardian has positively confirmed OPEN and entered:

    IMAGING_PERMITTED

a subsequent temporary loss of the observatory safety feed does not by itself
constitute a roof-closure emergency.

Therefore:

    OPEN -> UNKNOWN

during an established imaging session causes Guardian to:

- record the loss of authoritative roof information;
- report degraded observatory-status monitoring;
- continue polling the safety source;
- remain prepared to respond immediately when an authoritative state returns.

UNKNOWN alone does not trigger Safety Power-Off.

An authoritative:

    CLOSED

report remains the roof-closure trigger.

This distinction prevents a temporary network, API, server, or status-feed
failure from being incorrectly treated as physical roof movement.

### 7.6 Recovery From UNKNOWN

If authoritative communication returns:

    UNKNOWN -> OPEN

Guardian resumes normal monitoring.

If authoritative communication returns:

    UNKNOWN -> CLOSED

Guardian immediately evaluates the CLOSED condition using the normal
roof-closure protection rules.

### 7.7 Design Constraint

Guardian must not infer physical roof movement solely from loss of
communication with the observatory safety source.

Only an authoritative CLOSED state triggers roof-closure protection.

## 8. Mount Adapter

The mount adapter provides optional independent mount-control capabilities.

The mount is not a primary Guardian safety trigger.

Guardian does not monitor normal mount behavior in order to decide whether an
emergency exists.

The mount adapter is used after Guardian has determined that a shutdown or
emergency protection response is required.

### 8.1 Independence From ASIAIR

Mount-control capabilities used by Guardian must be independent of ASIAIR.

A control path that requires ASIAIR to remain operational does not qualify as
an independent Guardian protection path.

### 8.2 Mount Protection Levels

Guardian defines three mount protection levels.

#### Level 0 — No Independent Mount Control

Guardian cannot independently communicate with the mount.

Protection response:

    independent Safety Power-Off

Level 0 is a valid Guardian installation provided that the required
independent Safety Power Control capability is available.

#### Level 1 — Independent STOP

Guardian can independently command the mount to STOP but cannot reliably
determine or verify mount motion.

Protection response:

    request STOP
    proceed to independent Safety Power-Off

Guardian does not require confirmation of the STOP before proceeding to power
shutdown.

#### Level 2 — Independent STOP and State Verification

Guardian can independently determine mount motion and command and verify a
controlled STOP.

Standard mount states are:

    MOVING
    STATIONARY
    UNKNOWN
    UNAVAILABLE

The distinction between UNKNOWN and UNAVAILABLE is important.

UNKNOWN means the configured installation provides an independent mechanism
for determining mount state, but Guardian cannot currently determine that
state.

UNAVAILABLE means the installation does not provide an independent
mount-state capability. This is an accepted condition for a Level 0 or
otherwise appropriately configured installation and does not by itself
indicate a failure.

Protection response:

    MOVING:
        request STOP
        verify STOP where possible
        proceed to independent Safety Power-Off

    STATIONARY:
        proceed directly to independent Safety Power-Off

    UNKNOWN:
        request STOP where available
        proceed to independent Safety Power-Off

    UNAVAILABLE:
        proceed using the protection capabilities configured for the
        installation, including independent Safety Power-Off

Failure to verify STOP must never prevent the power shutdown.

### 8.3 Capability Interface

Mount adapters expose capabilities rather than requiring the Guardian Core to
identify specific mount brands.

Possible capabilities include:

    CAN_QUERY_MOTION
    CAN_STOP
    CAN_VERIFY_STOP
    CAN_RECOVER_CONNECTION
    CAN_QUERY_POSITION

The Guardian Core determines the available protection level from the
capabilities reported by the configured adapter.

### 8.4 STOP-Only Emergency Control

Guardian's emergency mount-control action is:

    STOP

Guardian must not automatically command:

    HOME
    PARK
    GOTO
    SLEW TO SAFE POSITION
    MERIDIAN FLIP
    POSITION RECOVERY

during an emergency protection response.

Guardian does not depend on a valid pointing model, current coordinates,
ASIAIR state, or known home position to execute its emergency protection.

The objective is to stop mount motion using the simplest available independent
command and then proceed to the independent power shutdown.

### 8.5 Bounded Mount Control

Mount communication and STOP attempts must use bounded timeouts.

A failed, unavailable, or unresponsive mount-control path must not delay the
independent power shutdown indefinitely.

### 8.6 Adapter Responsibility

The mount adapter is responsible for:

- protocol-specific communication;
- interpreting mount responses;
- determining motion where supported;
- issuing STOP where supported;
- verifying STOP where supported;
- bounded connection recovery where supported;
- returning standardized results to the Guardian Core.

The mount adapter must not decide whether an emergency exists.

That decision belongs exclusively to the Guardian Core.

## 9. Safety Power Architecture

Independent Safety Power-Off is a required Guardian protection
capability.

Guardian must be able to remove power from the ASIAIR and mount without
depending on ASIAIR itself.

The implementation may use one power controller or multiple independent
power controllers.

### 9.1 Power Source Versus Safety Power Control

Guardian distinguishes between:

    POWER SOURCE

and:

    SAFETY POWER CONTROL

A power source supplies electricity to equipment.

Examples include:

- utility power;
- UPS;
- battery backup.

A Safety Power Controller provides a control path through which Guardian
can independently command configured equipment power OFF.

Examples may include:

- TP-Link / Kasa devices;
- Digital Loggers Web Power Switch devices;
- network-controlled PDUs;
- controllable UPS load groups;
- network or USB relay systems;
- other supported power-control hardware.

Simply plugging equipment into a UPS does not provide Guardian Safety Power
Control.

A UPS satisfies the Safety Power requirement only when Guardian can
independently command the appropriate equipment load or outlet OFF through a
supported adapter.

### 9.2 Logical Power Roles

Guardian operates on logical equipment roles rather than physical outlet
numbers.

Initial roles are:

    ASIAIR
    MOUNT
    ACCESSORIES
    GUARDIAN_HOST

ASIAIR and MOUNT are required safety power-off roles.

ACCESSORIES is optional and may include equipment such as:

- power distribution boxes;
- dew-heater controllers;
- cameras;
- filter wheels;
- focusers;
- other imaging equipment.

GUARDIAN_HOST identifies the computer running Guardian.

GUARDIAN_HOST is always protected from automatic emergency shutdown.

### 9.3 Controller, Endpoint, and Role Mapping

Guardian distinguishes between a Safety Power Controller and a Safety Power
Endpoint.

A Safety Power Controller is the physical device through which Guardian
controls power.

Examples include a Kasa power strip, Pegasus power controller, EAGLE,
network PDU, controllable UPS, or relay system.

A Safety Power Endpoint is an independently controllable output, outlet,
relay, or load group provided by a Safety Power Controller.

Logical roles map to Safety Power Endpoints rather than directly to assumed
outlet numbers.

For example:

    ASIAIR
        -> controller_A / endpoint 2

    MOUNT
        -> controller_A / endpoint 3

or:

    ASIAIR
    MOUNT
        -> controller_A / endpoint 3

A logical role may map to one or more endpoints.

Multiple logical roles may share an endpoint when the installation is
intentionally wired that way.

Guardian must eliminate duplicate physical endpoint operations while still
recording the shutdown result for every affected logical role.

### 9.4 Power Dependencies

Safety Power topology may contain dependencies that are not represented by
simple role-to-endpoint mappings.

For example, a Guardian host computer may itself receive power from a
Pegasus controller while independently switched Pegasus outputs power the
ASIAIR and mount.

An EAGLE may simultaneously be:

- the computer running Guardian;
- a Safety Power Controller;
- the provider of independently switched power outputs for the ASIAIR,
  mount, and accessories.

These installations are valid when Guardian can control the required
ASIAIR and mount endpoints without removing power from itself or destroying
the control path needed to complete protection.

Guardian configuration and commissioning must therefore identify relevant
upstream power and control dependencies.

A shutdown endpoint is unsuitable for a required protection action if
switching that endpoint OFF would directly or indirectly remove power from
GUARDIAN_HOST before required protection actions can complete.

Likewise, Guardian must not intentionally remove an upstream controller or
communication dependency while that dependency is still required to execute
remaining protection actions.

### 9.5 Multiple Power Controllers

Guardian may use more than one Safety Power Adapter or Safety Power
Controller in the same installation.

The Guardian Core addresses logical roles.

The power-management layer resolves those roles to the appropriate
controller and endpoint or endpoints.

Failure of one controller must not prevent Guardian from attempting shutdown
through other configured controllers whose control paths remain available.

Shutdown sequencing must respect dependencies between controllers,
endpoints, the Guardian host, and required communication paths.

### 9.6 Protected Guardian Host

Guardian must never automatically remove power from the computer on which
Guardian itself is running as part of normal emergency Safety Power-Off.

GUARDIAN_HOST identifies that protected role.

An endpoint that directly powers GUARDIAN_HOST must not be selected as a
required emergency shutdown endpoint for ASIAIR, MOUNT, or ACCESSORIES.

An upstream power action that would indirectly remove power from
GUARDIAN_HOST is likewise prohibited while Guardian must remain operational
to complete required protection actions.

This does not prohibit GUARDIAN_HOST from receiving power from the same
Safety Power Controller that provides independently switchable endpoints to
ASIAIR, MOUNT, or ACCESSORIES.

For example, a Pegasus or EAGLE installation may be valid when Guardian
runs on a computer powered by or integrated with that controller while the
ASIAIR and mount remain independently switchable through separate endpoints.

Commissioning must prove that required emergency endpoints can be operated
without prematurely disabling GUARDIAN_HOST or the control path required to
complete protection.

### 9.7 Required Safety Power Capability

Guardian may enter normal ARMED operation only when commissioning has
established independently controllable Safety Power-Off for:

    ASIAIR
    MOUNT

The control path must remain usable when ASIAIR is unavailable.

The ASIAIR and mount may use:

- separate endpoints;
- a shared endpoint;
- separate Safety Power Controllers;
- the same Safety Power Controller.

The Guardian host may share a controller with protected equipment provided
the required shutdown endpoints do not remove Guardian host power and do not
prematurely destroy the required control path.

The requirement is functional independence from ASIAIR and preservation of
Guardian's protection path, not a particular wiring topology.

### 9.8 Safety Power Adapter Interface

Guardian uses a hardware-neutral Safety Power Adapter interface.

The Guardian Core and power-management layer must not contain
manufacturer-specific logic. Hardware-specific adapters translate the generic
Guardian operations into the protocol required by the configured controller.

Controllers may include Kasa, Pegasus, EAGLE, Wanderer, SVBONY, network PDUs,
controllable UPS outputs, relay systems, or other supported hardware.

A minimum adapter exposes operations equivalent to:

    controller_id
    supports_verification
    check_endpoint(endpoint)
    power_off(endpoint)

Controllers capable of reporting endpoint state additionally expose:

    get_power_state(endpoint)

using the normalized states:

    ON
    OFF
    UNKNOWN

Controllers capable of explicit shutdown verification may additionally expose:

    verify_off(endpoint)

check_endpoint(endpoint) is a non-destructive runtime operation. It confirms
that Guardian can communicate with the configured controller endpoint and that
the endpoint matches the configured controller identity. It must not change
endpoint power state.

Runtime readiness checks must use non-destructive operations. Guardian must
not cycle or remove equipment power merely to determine whether a system is
ready to image.

Physical proof that an endpoint actually removes power from its intended
equipment belongs to commissioning rather than routine runtime readiness.

Adapters must use bounded communication timeouts.

Where the underlying controller supports multiple operations in one
connection or session, the adapter should avoid unnecessary reconnections
during an emergency shutdown.

### 9.9 Shutdown Result States

Guardian distinguishes between a command being issued and shutdown being
verified.

Power-action results should include at least:

    VERIFIED_OFF
    COMMANDED_UNVERIFIED
    FAILED

VERIFIED_OFF means Guardian independently confirmed that the configured
endpoint is OFF.

COMMANDED_UNVERIFIED means the OFF command was issued but the configured
hardware cannot provide reliable independent confirmation.

FAILED means Guardian could not establish that the required shutdown command
was successfully executed.

Guardian must never report COMMANDED_UNVERIFIED as VERIFIED_OFF.

### 9.10 Verification

When the power controller can report current endpoint state, Guardian
must use that capability to verify shutdown.

Verification should use a fresh state query rather than assuming that a
successful command response means power has actually been removed.

Unverified or failed shutdown actions normally remain eligible for emergency
retry. The specific Safety Power capability-loss exception defined in
Section 10.8 applies when Guardian has independently verified that the mount
has stopped and continued power retry is no longer required to establish the
immediate safe state.

### 9.11 Emergency Shutdown Execution

When Safety Power-Off is required, Guardian resolves the configured
logical roles into Safety Power Endpoints.

Typical shutdown targets are:

    ASIAIR
    MOUNT
    ACCESSORIES

Guardian must:

1. exclude endpoints that would directly or indirectly disable GUARDIAN_HOST;
2. preserve controller and communication dependencies required for remaining actions;
3. eliminate duplicate physical endpoints caused by shared role mappings;
4. issue OFF commands using the appropriate Safety Power Adapter or adapters;
5. verify each endpoint where supported;
6. record the result for each logical role;
7. retry unresolved required shutdown actions.

### 9.12 Adapter Responsibility

Each Safety Power Adapter is responsible for:

- controller-specific communication;
- authentication where required;
- endpoint discovery or addressing;
- issuing OFF commands;
- querying power state where supported;
- bounded connection attempts;
- returning standardized results.

The adapter must not decide whether a Guardian emergency exists.

That decision belongs exclusively to the Guardian Core.

## 10. Protection Strategy

Guardian uses a layered protection sequence after the Guardian Core determines
that shutdown or emergency protection is required.

The protection sequence distinguishes between:

    REQUIRED SAFETY ACTIONS

and:

    BEST-EFFORT SAFETY ACTIONS

### 10.1 Protection Triggers

Guardian recognizes three classes of events that can require protection during
an active imaging session.

#### 1. Authoritative Roof Closure

If the authoritative roof state becomes:

    CLOSED

while ASIAIR remains ONLINE, Guardian requires shutdown.

This does not require Guardian to determine whether the closure was expected
or unexpected.

#### 2. Established ASIAIR Connection Loss

If the roof is:

    OPEN

and an ASIAIR connection that was previously established during the current
armed session becomes:

    LOST

Guardian requires emergency protection.

Guardian does not need to determine whether the cause was failure of ASIAIR,
failure of the ASIAIR network interface, or failure of the communication path.

Loss of the established control path is sufficient.

#### 3. Required Protection-Capability Loss

If Guardian loses a protection capability that is required for the configured
installation while an imaging session is active, Guardian must not continue
the session as though full protection remained available.

Examples include loss of:

- a required Safety Power Control path;
- the observatory network carrying required protection services;
- another commissioned protection path required for Guardian to execute its
  mandatory safety response.

Guardian must initiate shutdown using whatever independent protection paths
remain available.

Protection-capability loss does not establish that the observatory or imaging
equipment is physically unsafe.

For example, an observatory network may fail while the roof remains open,
ASIAIR remains operational, and the mount continues normally.

The reason for shutdown is that Guardian can no longer guarantee the
commissioned protection capability.

Guardian must report this distinction clearly to the operator.

A protection-capability-loss event should identify:

    capability or path lost
    last known equipment states
    remaining protection paths
    shutdown actions attempted
    shutdown actions completed
    unresolved required actions

Guardian must not report a protection-capability-loss event as an
authoritative roof closure or ASIAIR failure unless those conditions were
independently established.

#### Temporary Roof-Source Uncertainty

A temporary transition of the authoritative roof source to UNKNOWN is not,
by itself, equivalent to protection-capability loss.

If the roof source becomes UNKNOWN during established imaging while required
emergency protection paths remain available, Guardian follows the UNKNOWN
policy defined in the Observatory Safety Adapter section:

    report degraded monitoring
    continue polling
    do not infer physical roof movement

However, if the same infrastructure failure also removes a required
protection capability, the event is evaluated as required
protection-capability loss.

### 10.2 Required Safety Actions

The required Guardian shutdown targets are:

    ASIAIR POWER OFF
    MOUNT POWER OFF

These actions form Guardian's normal mandatory final protection path.

Guardian must attempt them during the initial protection sequence regardless
of whether optional or enhanced protection actions succeed.

The initial Safety Power-Off attempt is mandatory even when the triggering
event is loss of SAFETY_POWER_CONTROL itself. Persistent retry after that
initial attempt is subject only to the verified-STOP exception defined in
Section 10.8.

### 10.3 Best-Effort Safety Actions

Best-effort actions may include:

    controlled mount STOP
    mount STOP verification
    accessory power shutdown
    ASIAIR desktop application shutdown
    operator notifications
    other nonessential housekeeping

Failure of a best-effort action must not prevent or indefinitely delay
required safety actions.

### 10.4 Protection Sequence

When Guardian determines that protection is required:

    1. Record the triggering safety event.

    2. If independent mount STOP capability exists:
           determine mount state where supported;
           issue STOP when appropriate;
           verify STOP where supported.

    3. Proceed to independent Safety Power-Off regardless of the
       result of the mount STOP attempt.

    4. Command power OFF for:
           ASIAIR
           MOUNT

    5. Command power OFF for configured ACCESSORIES where applicable.

    6. Verify shutdown state for each target where supported.

    7. Record VERIFIED_OFF, COMMANDED_UNVERIFIED, or FAILED for each
       shutdown target.

    8. Latch the imaging session ABORTED.

    9. Arm the emergency retry engine for unresolved required actions,
       subject to the verified-STOP Safety Power capability-loss exception
       defined in Section 10.8.

   10. Notify the operator and perform non-safety-critical housekeeping.

### 10.5 STOP Must Not Block Power Removal

Independent mount STOP is an enhanced protection capability.

STOP attempts must use bounded timeouts.

The following outcomes all proceed to Safety Power-Off:

    STOP_VERIFIED
    STOP_COMMANDED_UNVERIFIED
    STOP_FAILED
    STOP_UNAVAILABLE

Guardian must never wait indefinitely for a mount STOP response before
attempting required power removal.

### 10.6 Meaning of ABORTED

ABORTED describes the imaging session state.

It means Guardian has determined that the session must not continue and has
initiated protection.

ABORTED does not mean that every safety action has succeeded.

Therefore Guardian may simultaneously report:

    SESSION = ABORTED

and:

    ASIAIR POWER = FAILED
    MOUNT POWER = VERIFIED_OFF

or other combinations of protection results.

This distinction is essential because Guardian must continue working on
actions that remain unresolved after the imaging session has already been
aborted. The verified-STOP Safety Power capability-loss exception in Section
10.8 determines when failed Safety Power actions no longer require persistent
retry.

### 10.7 Required Action Completion

A required shutdown action is resolved when Guardian reaches the strongest
state that the configured hardware can reliably provide.

For hardware with independent state verification:

    VERIFIED_OFF

is required.

For hardware that cannot independently report power state:

    COMMANDED_UNVERIFIED

may be the strongest available result, but Guardian must clearly identify
that reduced verification capability to the operator.

Commissioning must record whether each required power path is independently
verifiable.

### 10.8 Emergency Retry

FAILED required Safety Power actions normally remain unresolved and enter the
emergency retry engine.

Emergency retry continues independently of the ABORTED session state.

For ROOF_CLOSED and ASIAIR_LOST protection events, successful mount STOP does
not replace configured Safety Power-Off. Failed required power actions remain
eligible for retry even when independent mount STOP was verified.

Required protection-capability loss has one specific exception.

If SAFETY_POWER_CONTROL itself is lost during active imaging, Guardian must:

1. determine that the active imaging session must be aborted;
2. attempt independent mount STOP where available;
3. verify STOP where independent verification is available;
4. attempt the configured Safety Power-Off during the initial protection
   sequence even though the Safety Power path has been reported unavailable.

If independent mount STOP is positively verified, Guardian has established the
immediate safe stationary mount state. Failed Safety Power actions from that
incident do not require persistent emergency retry solely to remove power from
the already secured, aborted system.

A successful STOP command without independent STOP verification is not
sufficient for this exception.

If STOP is unavailable, fails, times out, or cannot be positively verified,
failed required Safety Power actions remain unresolved and Guardian continues
retrying them when the power-control path becomes available.

This exception changes only persistent retry behavior after loss of the Safety
Power capability. It does not remove the initial Safety Power-Off attempt, does
not permit automatic resumption of imaging, and does not weaken the
ROOF_CLOSED or ASIAIR_LOST protection sequences.

Best-effort actions may have their own bounded retry behavior, but they must
never prevent required emergency actions.

### 10.9 Independent Failure Paths

Guardian must attempt each available protection path independently.

For example:

    mount STOP failure

must not prevent:

    ASIAIR power shutdown
    MOUNT power shutdown
    ACCESSORIES power shutdown

Likewise, failure of one power controller must not prevent Guardian from
attempting required actions through another configured controller.

### 10.10 Operator Reporting

Guardian status and alerts must distinguish:

    what triggered protection;
    what actions were attempted;
    what actions succeeded;
    what actions remain unresolved;
    whether results were verified or unverified;
    whether emergency retry remains active.

Guardian must not summarize a partially completed protection sequence simply
as successful.

## 11. ASIAIR Connection-Loss Protection

Guardian distinguishes normal startup from loss of an established controller.

ASIAIR that has not yet been observed online during the current armed session
does not constitute a controller-loss emergency.

Once ASIAIR has been observed online, Guardian considers that connection
established for the session.

If the established ASIAIR connection is subsequently lost while the
observatory roof remains OPEN, Guardian initiates emergency protection.

The response is:

    if independent mount STOP is available:
        attempt controlled STOP
        verify STOP where supported

    independently remove power from:
        ASIAIR
        MOUNT
        configured imaging accessories

    verify power removal
    retry unresolved actions
    latch session ABORTED
    notify operator

If mount state is known to be MOVING, Guardian attempts STOP before power
removal.

If mount state is UNKNOWN, Guardian attempts STOP where supported and then
continues to power removal.

If mount state is STATIONARY, Guardian may omit the STOP command, but the
unexpected loss of ASIAIR while the roof remains open still requires the
configured Safety Power-Off.

Failure of mount communication or STOP verification must never prevent
Guardian from attempting independent power shutdown.

---

## 12. Roof-Closure Protection

If the observatory roof becomes CLOSED while ASIAIR remains online, Guardian
initiates shutdown.

Guardian does not attempt to determine whether the closure is an unexpected
mid-session event or the observatory's normal scheduled end-of-night closure.

The safety rule is:

    ROOF CLOSED + ASIAIR ONLINE = SHUT DOWN

If independent mount control is available:

    if MOVING:
        attempt controlled STOP and verify where supported

    if STATIONARY:
        no STOP is required

    if UNKNOWN:
        attempt controlled STOP where supported

Guardian then independently removes power from:

    ASIAIR
    MOUNT
    configured imaging accessories

and verifies the shutdown.

If the roof closes after ASIAIR has already become offline, no emergency
action is required:

    ROOF CLOSED + ASIAIR OFFLINE = SAFE / NO ACTION

This represents the expected condition after a normal completed imaging
session.

Failure or absence of independent mount control must never prevent Guardian
from executing the configured power shutdown.

---

## 13. Emergency Retry Engine

Emergency actions must not be single-attempt operations.

Guardian maintains unresolved protection actions after the session becomes
ABORTED.

A staged retry schedule should permit rapid initial retries followed by less
frequent persistent attempts.

Retries continue until:

- the required safe state is verified; or
- the operator explicitly intervenes.

Guardian must never report a protection action as VERIFIED merely because
the command was sent.

Where the configured hardware supports independent state verification,
Guardian must verify the resulting safe state.

Where independent verification is not available, Guardian may report
COMMANDED_UNVERIFIED as the strongest available result and must clearly
identify that limitation to the operator.

---

## 14. Operator Services

Operator services are separate from the safety engine.

They include:

- status display;
- ARM;
- DISARM;
- alert acknowledgement;
- event log access;
- notifications;
- diagnostics.

Failure of the user interface must not stop Guardian protection.

Closing the Guardian user interface must not stop the Guardian service.

---

## 15. Configuration

Guardian configuration describes the installation.

It should contain sections similar to:

    guardian
    asiair
    observatory
    mount
    power
    notifications
    logging

Configuration must not contain executable safety logic.

Passwords and other credentials should not be stored in plain text when a
platform credential store is available.

---

## 16. Setup, Commissioning, Readiness, and Arming

Guardian distinguishes between three installation states:

    COMMISSIONED
    READY
    ARMED

These states answer different questions.

COMMISSIONED means the installation has demonstrated that its configured
safety capabilities work as intended.

READY means all required commissioned protection capabilities are currently
available.

ARMED means Guardian is actively supervising the installation and is
authorized to execute protection when required.

### 16.1 Commissioning Principle

Guardian must not assume that an installation is safe merely because its
configuration is syntactically valid or because a device responds over the
network.

Commissioning proves the relationship between Guardian's configuration and
the actual installation.

A new installation must successfully complete commissioning before Guardian
permits normal ARMED operation.

### 16.2 Required Commissioning Tests

Commissioning must establish at least:

    ASIAIR monitoring path              VERIFIED
    observatory safety source           VERIFIED
    ASIAIR Safety Power role            VERIFIED
    mount Safety Power role             VERIFIED
    Guardian host protection            VERIFIED
    simultaneous required paths         VERIFIED
    protection logic validation         VERIFIED

Guardian must verify that the required ASIAIR and mount Safety Power roles can
be controlled independently of ASIAIR.

The ASIAIR and mount roles may map to separate Safety Power Endpoints or
to the same intentionally shared endpoint.

A shared endpoint may satisfy both required roles when commissioning confirms
that switching that endpoint OFF removes power from both devices.

Commissioning must also verify that the required endpoints remain controllable
without ASIAIR and that their use does not prematurely disable GUARDIAN_HOST
or another control path required to complete protection.

### 16.3 Physical Safety Power Verification

Guardian must not consider a Safety Power role VERIFIED merely because a
controller reports that a configured endpoint exists.

Initial commissioning should physically exercise each required Safety Power
mapping.

A typical test is:

    1. Operator confirms that the equipment is safe to power off.
    2. Guardian identifies the configured controller and endpoint.
    3. Guardian commands the endpoint OFF.
    4. Guardian verifies the endpoint OFF electronically where supported.
    5. Operator confirms that the expected equipment actually lost power.
    6. Guardian records the role-to-endpoint mapping as VERIFIED.
    7. Power is restored only as part of the controlled commissioning
       procedure and with operator awareness.

When ASIAIR and mount intentionally share one endpoint, one physical
switching test may verify both roles if the operator confirms that both
devices lost power.

Guardian must never automatically test an endpoint that would remove power
from GUARDIAN_HOST.

Commissioning must fail if a required Safety Power shutdown endpoint would
directly or indirectly remove power from GUARDIAN_HOST before required
protection actions can complete.

Commissioning must also verify that operating one required shutdown endpoint
does not prematurely destroy a controller, network, USB, or other control
path needed to execute the remaining required shutdown actions.

GUARDIAN_HOST may share a Safety Power Controller with ASIAIR, MOUNT, or
ACCESSORIES when those roles use independently controllable endpoints and
the required protection sequence preserves Guardian and its necessary
control paths.

### 16.4 Optional and Enhanced Capability Tests

Independent mount control is not required for a valid Guardian installation.

Where configured, commissioning should test enhanced capabilities such as:

    independent mount communication
    mount motion detection
    independent mount STOP
    STOP verification
    mount connection recovery
    UPS monitoring
    accessory Safety Power-Off
    power-state verification

Capabilities not provided by the installation are recorded as:

    UNAVAILABLE

This is different from UNKNOWN or FAILED.

UNAVAILABLE means the capability is not part of the commissioned installation.

UNKNOWN or FAILED indicates a problem with a capability that is expected to
exist.

### 16.5 Functional Commissioning and Logic Validation

Guardian distinguishes between:

    FUNCTIONAL COMMISSIONING
    LOGIC VALIDATION

Functional commissioning exercises real hardware where doing so is safe and
appropriate.

Examples include:

    Safety Power switching
    power-state queries
    mount STOP
    mount-state queries

Logic validation tests Guardian's safety decisions using controlled or
simulated inputs.

Examples include:

    simulated roof closure
    simulated established ASIAIR connection loss
    simulated required protection-capability loss
    shutdown sequencing
    retry behavior
    ABORTED-state behavior

Guardian must not require deliberately creating hazardous observatory
conditions merely to complete commissioning.

For example, commissioning must not require:

    physically closing a roof over an operating rig
    deliberately causing a facility power outage
    deliberately disabling required observatory infrastructure

### 16.6 Commissioning Record

Successful commissioning produces a persistent commissioning record.

The record should include at least:

    commissioning date
    safety-critical configuration fingerprint
    required test results
    Safety Power role mappings
    protection capabilities
    mount protection level
    verification capabilities
    logic-validation results

The commissioning record survives normal Guardian and host-computer restarts.

### 16.7 Configuration Fingerprint

Guardian should calculate a fingerprint representing safety-critical
configuration.

Changes to safety-critical configuration invalidate the existing
commissioning record and require recommissioning.

Examples include changes to:

    Safety Power controller type or address
    Safety Power role-to-endpoint mappings
    observatory safety-source configuration
    ASIAIR monitoring configuration
    Guardian network topology relevant to protection
    mount adapter or mount-control configuration
    Guardian-host power mapping

Routine operational changes do not invalidate commissioning.

Examples include:

    restarting Guardian
    restarting the Guardian host
    changing an imaging target
    changing an ASIAIR imaging plan
    normal nightly ASIAIR power cycling

### 16.8 Physical Installation Changes

Guardian cannot reliably detect every physical change to an installation.

For example, Guardian may be unable to determine that an operator or
technician moved the mount power cable from one PDU channel to another while
leaving the Guardian configuration unchanged.

The operator is responsible for recommissioning Guardian after known physical
changes affecting:

    power wiring
    Safety Power distribution
    network topology
    ASIAIR hardware or connection method
    mount hardware
    observatory safety source
    Guardian host connectivity
    other commissioned protection paths

Guardian should provide a clear Recommission or Verify Installation function
for this purpose.

Commissioning does not expire solely because a fixed amount of time has
passed.

Periodic verification may be recommended, but an arbitrary elapsed-time
threshold does not automatically invalidate an otherwise unchanged
commissioning record.

### 16.9 Readiness

Commissioning establishes what the installation can do.

Readiness determines whether the required commissioned capabilities are
available now.

Readiness checks must be non-destructive.

They should not power-cycle equipment merely to permit normal arming.

Before entering normal protected operation, Guardian should confirm the
current availability of required paths including:

    observatory safety source
    required Safety Power Controller(s)
    required Safety Power roles
    required network interfaces and routes
    other protection capabilities designated as required by commissioning

The ASIAIR itself does not have to be online when Guardian becomes ARMED.

Guardian may begin with:

    ASIAIR = NOT_ESTABLISHED

and wait for the normal transition:

    NOT_ESTABLISHED -> ONLINE

Only after ASIAIR has been established ONLINE during the current armed session
can later loss become:

    ONLINE -> LOST

### 16.10 Arming Before Imaging

The observatory roof does not have to be OPEN for Guardian to become ARMED.

A normal pre-session state may be:

    GUARDIAN = ARMED
    SESSION = WAITING_FOR_ROOF
    ROOF = CLOSED
    ASIAIR = NOT_ESTABLISHED

Guardian waits for the conditions required to permit imaging.

Before entering IMAGING_PERMITTED, all required commissioned protection
capabilities must be READY.

If a required capability is unavailable before imaging begins, Guardian does
not create an emergency merely because the prerequisite is missing.

Instead it remains in a non-imaging state and reports why imaging is not
permitted.

For example:

    GUARDIAN = ARMED
    SESSION = WAITING_FOR_PROTECTION
    ROOF = OPEN
    ASIAIR = ONLINE
    SAFETY POWER = UNAVAILABLE
    IMAGING_PERMITTED = NO

### 16.11 Loss of Readiness During Imaging

The meaning of a missing required capability changes after imaging has been
permitted.

Before imaging:

    required capability unavailable
        -> do not permit imaging

During an active imaging session:

    previously available required capability lost
        -> protection-capability-loss event
        -> initiate shutdown using remaining independent paths
        -> latch session ABORTED

This implements the principle that Guardian must not knowingly continue an
imaging session after losing a protection capability on which the commissioned
safety design depends.

### 16.12 Recommissioning

Recommissioning is required when:

- Guardian detects a safety-critical configuration change;
- the operator reports a relevant physical installation change;
- a previously commissioned capability is intentionally replaced or
  reconfigured;
- commissioning records are absent or invalid.

Recommissioning is not required merely because Guardian or the host computer
restarted.

Guardian should clearly explain which change invalidated commissioning and
which tests must be repeated.

---

## 17. Capability Model

Guardian describes an installation by protection capabilities rather than by
a simple supported/unsupported device list.

Required Guardian capabilities include:

    ASIAIR_MONITORING
    OBSERVATORY_SAFETY_MONITORING
    SAFETY_POWER_CONTROL

Enhanced capabilities may include:

    SAFETY_POWER_STATE_VERIFICATION
    INDEPENDENT_MOUNT_MOTION
    INDEPENDENT_MOUNT_STOP
    MOUNT_STOP_VERIFICATION
    MOUNT_CONNECTION_RECOVERY
    INDEPENDENT_MOUNT_POSITION
    UPS_MONITORING
    ACCESSORY_SAFETY_POWER_CONTROL

Capabilities are interpreted together with the commissioning record.

A capability may be:

    AVAILABLE
    UNAVAILABLE
    UNKNOWN
    FAILED

UNAVAILABLE means the capability is intentionally not provided by the
commissioned installation.

UNKNOWN or FAILED indicates a problem determining or using a capability that
the commissioned installation expects to provide.

Required capabilities must be available before Guardian permits imaging.

Loss of a required capability during an active imaging session is evaluated
as a protection-capability-loss event.

This capability model permits Guardian to support new equipment through
adapters without changing the Guardian Core safety policy.

---

## 18. Adapter Interface

Adapters must have a small, documented interface.

Each adapter is responsible for:

- device communication;
- protocol-specific interpretation;
- bounded timeouts;
- connection recovery where appropriate;
- returning standardized states;
- never falsely reporting success.

Adapters must not make Guardian safety-policy decisions.

---

## 19. Reference Installation

The original Guardian installation serves as the reference implementation.

Its architecture is:

    Controller:
        ASIAIR Plus

    Mount:
        Sky-Watcher Wave 150i

    Independent mount control:
        SynScan / Sky-Watcher motor-controller network path

    Observatory safety:
        Alpaca SafetyMonitor

    Safety Power:
        Kasa HS300

    Guardian host:
        macOS computer independent of ASIAIR

This installation is a reference adapter set, not a hard-coded Guardian
architecture.

---

## 20. Backward Compatibility

Guardian 1.0 development must not modify or destabilize the proven production
Guardian installation.

The existing implementation remains the operational baseline while the
portable architecture is developed and tested separately.

Existing safety behavior should be preserved unless a change is explicitly
identified, reviewed, and tested.

---

## 21. Initial Guardian 1.0 Scope

Guardian 1.0 is intended for:

- ASIAIR-controlled imaging systems;
- unattended or remote operation;
- installations with an external safety or roof-status source;
- installations with an independent Guardian computer;
- installations with Safety Power Control capable of independently removing
  power from both the ASIAIR and mount.

The ASIAIR and mount Safety Power roles may use separate Safety Power
Endpoints or an intentionally shared endpoint, provided commissioning verifies
that both required roles are satisfied and that the protection sequence
preserves GUARDIAN_HOST and all control paths required to complete shutdown.

Guardian 1.0 is not intended to replace:

- ASIAIR imaging plans;
- NINA;
- full observatory automation software;
- dome-control software;
- weather forecasting systems.

Guardian reacts to authoritative safety information supplied by the
observatory or configured safety source.

---

## 22. Development Rule

Safety comes before convenience.

New hardware support must be implemented through adapters and tested without
weakening the Guardian Core safety invariants.

A new feature must never silently reduce an existing protection path.
