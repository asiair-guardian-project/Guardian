"""Commissioning rehearsal: real Kasa shutdown path, simulated triggers.

Runs the SAME gate, supervisor, application and one-connection Kasa shutdown
that the armed monitor uses, against the real strip, with the roof, ASIAIR and
UPS inputs simulated. It exists to produce evidence for the integrated
emergency-shutdown commissioning check. It never approves commissioning.

Safety design:
  * a throwaway recovery file in a temporary folder: the real recovery file and
    the real operator socket are never touched;
  * preflight reads the real outlets first and refuses unless every target is
    readable with the expected name and at least one is ON (a rehearsal on
    outlets that are already off proves almost nothing);
  * protected outlets (the Mac mini) must be readable before, and must be
    unchanged after, or the rehearsal FAILS;
  * only the three configured shutdown targets can ever be switched (the
    Starfront wiring); outlet 1 is not among them;
  * after the run the outlets are read again on a FRESH connection, independent
    of the one that sent the commands.
The operator powers the equipment back on afterwards, as after any abort.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import (
    REQUIRED_COMMISSIONING_CHECKS,
    CommissioningResult,
    CommissioningStatus,
)
from modules.guardian_types import (
    ProtectionTrigger,
    RoofState,
    SafetyPowerState,
    SessionState,
)
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_layout import starfront_layout
from modules.guardian_v1_starfront_kasa_integration import (
    compose_starfront_kasa_integration,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.runtime_supervisor import RuntimeSupervisor
from modules.ups_adapter import UpsReading

SCHEMA = "guardian-rehearsal-v1"
CONFIRM_TOKEN = "CUT_OUTLETS_2_3_4"          # the Starfront wiring; other layouts: layout.confirm_token
DEFAULT_PROTECTED = ((1, "Mac Mini"),)

EXPECTED_TRIGGER = {
    "roof-closed": ProtectionTrigger.ROOF_CLOSED,
    "asiair-lost": ProtectionTrigger.ASIAIR_LOST,
    "ups-low": ProtectionTrigger.UPS_LOW_BATTERY,
    "internal-fault": ProtectionTrigger.INTERNAL_FAULT,
    "restart-while-armed": ProtectionTrigger.RESTART_WHILE_ARMED,
}
SCENARIOS = tuple(EXPECTED_TRIGGER)


class RehearsalRefused(RuntimeError):
    """A preflight check failed. Nothing was switched."""


def target_requests(layout=None):
    return [(t.number, t.alias) for t in (layout or starfront_layout()).targets]


# --- simulated inputs ------------------------------------------------------------


class SimRoof:
    def __init__(self):
        self.state = RoofState.OPEN

    def observe(self):
        return ObservatorySafetyObservation(
            state=self.state, observed_at=datetime.now(timezone.utc)
        )


class SimAsiair:
    def __init__(self):
        self.reachable = True

    def is_reachable(self):
        return self.reachable


class SimUps:
    def __init__(self):
        self.reading = UpsReading(on_battery=False, battery_percent=100)

    def read(self):
        return self.reading


class FaultInjector:
    """Wraps the real observation runtime; raises on demand."""

    def __init__(self, inner):
        self._inner = inner
        self.fault = False

    def run_cycle(self, *, armed, now):
        if self.fault:
            raise RuntimeError("rehearsal: injected Guardian fault")
        return self._inner.run_cycle(armed=armed, now=now)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TimedTransport:
    """Delegates to the real transport and times the batch calls."""

    _TIMED = ("power_off_outlets", "get_outlet_states")

    def __init__(self, inner, clock):
        self._inner = inner
        self._clock = clock
        self.command_seconds = []
        self.verify_seconds = []

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)  # AttributeError if unsupported

        if name not in self._TIMED:
            return attribute

        bucket = self.command_seconds if name == "power_off_outlets" else self.verify_seconds

        def timed(*args, **kwargs):
            start = self._clock()
            try:
                return attribute(*args, **kwargs)
            finally:
                bucket.append(round(self._clock() - start, 3))

        return timed


# --- result ----------------------------------------------------------------------


@dataclass
class RehearsalResult:
    scenario: str
    passed: bool = False
    weak_evidence: bool = False
    expected_trigger: str = ""
    observed_triggers: list = field(default_factory=list)
    unresolved_actions: list = field(default_factory=list)
    session_state: str = ""
    outlets_before: dict = field(default_factory=dict)
    outlets_after: dict = field(default_factory=dict)
    protected_before: dict = field(default_factory=dict)
    protected_after: dict = field(default_factory=dict)
    seconds_trigger_to_resolved: float | None = None
    batch_command_seconds: list = field(default_factory=list)
    verify_seconds: list = field(default_factory=list)
    cycles: int = 0
    notes: list = field(default_factory=list)
    started_at_utc: str = ""
    finished_at_utc: str = ""

    def as_evidence(self, *, configuration_fingerprint, kasa_host) -> dict:
        data = {
            "schema": SCHEMA,
            "commissioning_authorized": False,
            "note": "Rehearsal evidence only. It does not approve commissioning.",
            "configuration_fingerprint": configuration_fingerprint,
            "kasa_host": kasa_host,
        }
        data.update(self.__dict__)
        return data


def _names(states):
    return {str(number): (state.name if state else "UNREADABLE")
            for number, state in states.items()}


# --- preflight -------------------------------------------------------------------


def preflight(transport, *, protected=None, allow_already_off=False, layout=None):
    """Read the real outlets; raise RehearsalRefused if unsafe. Switches nothing."""

    layout = layout or starfront_layout()
    protected = tuple(protected) if protected is not None else (layout.host,)
    targets = target_requests(layout)

    try:
        before = transport.get_outlet_states(targets)
        protected_before = transport.get_outlet_states(list(protected))
    except Exception as error:
        raise RehearsalRefused(f"could not read the strip: {error}") from error

    unreadable = sorted(n for n, state in before.items() if state is None)

    if unreadable:
        raise RehearsalRefused(
            f"outlet(s) {unreadable} unreadable or not named as expected"
        )

    lost = sorted(n for n, state in protected_before.items() if state is None)

    if lost:
        raise RehearsalRefused(
            f"protected outlet(s) {lost} unreadable or not named as expected"
        )

    if not any(state is SafetyPowerState.ON for state in before.values()):
        if not allow_already_off:
            raise RehearsalRefused(
                "all three target outlets are already OFF; a rehearsal would "
                "prove very little. Power the equipment on first (or pass "
                "--allow-already-off for a commands-only check)."
            )

    return before, protected_before


# --- the rehearsal -----------------------------------------------------------------


def _build_stack(workdir, *, transport, fingerprint, roof, asiair, ups, inject_faults, layout=None):
    layout = layout or starfront_layout()
    store = GuardianV1RecoveryStore(Path(workdir) / "recovery.json")

    if not store.path.exists():
        store.write(RuntimeSupervisor().export_recovery_state())

    application = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES),
        recovery_store=store,
        allow_restart_abort=True,
    )
    observation = compose_starfront_kasa_integration(
        application=application,
        asiair_host="rehearsal.invalid",
        alpaca_host="rehearsal.invalid",
        alpaca_port=443,
        alpaca_device_number=17,
        kasa_host="rehearsal.invalid",
        commissioning=CommissioningStatus(
            results={c: CommissioningResult.VERIFIED
                     for c in REQUIRED_COMMISSIONING_CHECKS},
            configuration_fingerprint=fingerprint,
        ),
        configuration_fingerprint=fingerprint,
        kasa_transport=transport,
        power_mapping=layout.mapping,
        asiair_adapter=asiair,
        observatory_adapter=roof,
        ups_adapter=ups,
    )
    runtime = FaultInjector(observation) if inject_faults else observation
    gate = GuardianV1ArmedGate(application=application, observation_runtime=runtime)
    application.mode.enable_hardware_execution()  # inside this process only
    return application, gate, runtime


def _cycle(gate, result):
    result.cycles += 1

    try:
        gate.cycle(now=datetime.now(timezone.utc))
    except Exception as error:  # a fault scenario raises by design
        result.notes.append(f"cycle {result.cycles}: {type(error).__name__}: {error}")


def run_rehearsal(
    *,
    scenario,
    transport,
    configuration_fingerprint,
    protected=None,
    allow_already_off=False,
    layout=None,
    settle_cycles=2,
    max_cycles=40,
    cycle_pause_seconds=1.0,
    sleep=time.sleep,
    clock=time.monotonic,
    workdir=None,
):
    if scenario not in EXPECTED_TRIGGER:
        raise RehearsalRefused(f"unknown scenario {scenario!r}")

    layout = layout or starfront_layout()
    protected = tuple(protected) if protected is not None else (layout.host,)
    before, protected_before = preflight(
        transport, protected=protected, allow_already_off=allow_already_off, layout=layout
    )

    result = RehearsalResult(scenario=scenario)
    result.expected_trigger = EXPECTED_TRIGGER[scenario].name
    result.outlets_before = _names(before)
    result.protected_before = _names(protected_before)
    result.weak_evidence = not any(
        state is SafetyPowerState.ON for state in before.values()
    )
    result.started_at_utc = datetime.now(timezone.utc).isoformat()

    own_dir = workdir is None
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="guardian-rehearsal-"))
    fingerprint = f"rehearsal:{configuration_fingerprint}"
    timed = TimedTransport(transport, clock)
    roof, asiair, ups = SimRoof(), SimAsiair(), SimUps()

    try:
        application, gate, runtime = _build_stack(
            workdir, transport=timed, fingerprint=fingerprint, roof=roof,
            asiair=asiair, ups=ups, inject_faults=(scenario == "internal-fault"), layout=layout,
        )

        if not gate.arm():
            raise RehearsalRefused("the rehearsal gate refused ARM; nothing switched")

        for _ in range(max(1, settle_cycles)):
            _cycle(gate, result)
            sleep(cycle_pause_seconds)

        if application.supervisor.incident is not None:
            result.notes.append("an incident appeared before the trigger was injected")

        if scenario == "restart-while-armed":
            # Guardian 'dies' while armed: discard it, relaunch on the same file.
            application, gate, runtime = _build_stack(
                workdir, transport=timed, fingerprint=fingerprint, roof=roof,
                asiair=asiair, ups=ups, inject_faults=False, layout=layout,
            )
        elif scenario == "roof-closed":
            roof.state = RoofState.CLOSED
        elif scenario == "asiair-lost":
            asiair.reachable = False
        elif scenario == "ups-low":
            ups.reading = UpsReading(on_battery=True, battery_percent=10)
        elif scenario == "internal-fault":
            runtime.fault = True

        injected_at = clock()

        for _ in range(max_cycles):
            _cycle(gate, result)
            incident = application.supervisor.incident

            if incident is not None and not incident.unresolved_actions:
                break

            sleep(cycle_pause_seconds)

        incident = application.supervisor.incident
        result.session_state = application.supervisor.session_state.name

        if incident is not None:
            result.observed_triggers = sorted(t.name for t in incident.triggers)
            result.unresolved_actions = sorted(a.name for a in incident.unresolved_actions)
            if not incident.unresolved_actions:
                result.seconds_trigger_to_resolved = round(clock() - injected_at, 3)

        result.batch_command_seconds = list(timed.command_seconds)
        result.verify_seconds = list(timed.verify_seconds)

        # Independent confirmation on a fresh connection, not the one that sent
        # the commands.
        after = transport.get_outlet_states(target_requests(layout))
        protected_after = transport.get_outlet_states(list(protected))
        result.outlets_after = _names(after)
        result.protected_after = _names(protected_after)

        result.passed = bool(
            incident is not None
            and result.observed_triggers == [result.expected_trigger]
            and not result.unresolved_actions
            and application.supervisor.session_state is SessionState.ABORTED
            and all(state is SafetyPowerState.OFF for state in after.values())
            and result.protected_after == result.protected_before
        )

        if not result.passed:
            result.notes.append("FAIL: see the fields above for what did not match")
    finally:
        result.finished_at_utc = datetime.now(timezone.utc).isoformat()
        if own_dir:
            shutil.rmtree(workdir, ignore_errors=True)

    return result


def write_evidence(result, directory, *, configuration_fingerprint, kasa_host) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"rehearsal_{result.scenario}_{stamp}.json"
    path.write_text(json.dumps(
        result.as_evidence(
            configuration_fingerprint=configuration_fingerprint,
            kasa_host=kasa_host,
        ), indent=2, sort_keys=True))
    path.chmod(0o600)
    return path
