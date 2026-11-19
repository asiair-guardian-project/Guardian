"""Restart-while-armed abort: Guardian restarts while an armed session is on
record -> power the rig off, latch ABORTED, wait for the operator.

Disk-backed, simulated power executor only. No network, no hardware.
"""
import pytest

from modules.commissioning import CommissioningStatus
from modules.guardian_types import (
    AsiairState,
    ProtectionAction,
    ProtectionTrigger,
    RoofState,
    SafetyPowerResult,
    SafetyPowerRole,
    SessionState,
)
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_login_notice import recovery_notice
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.safety_power_manager import SafetyPowerRoleRecord

ALL_ROLES = {
    SafetyPowerRole.ASIAIR,
    SafetyPowerRole.MOUNT,
    SafetyPowerRole.ACCESSORIES,
}


def marker(session="IMAGING_PERMITTED", clean=False):
    """What the recovery file looks like when Guardian stopped while armed."""
    return dict(
        schema_version=2,
        active_incident=None,
        abort_acknowledged=False,
        incident_history=[],
        session_state=session,
        shutdown_clean=clean,
        recovery_required=False,
    )


class FakePower:
    """Simulated safety-power executor with a scripted list of outcomes."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes) or [SafetyPowerResult.VERIFIED_OFF]
        self.calls = []

    def __call__(self, roles):
        self.calls.append(set(roles))
        result = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        return [SafetyPowerRoleRecord(role=r, endpoint=None, result=result) for r in roles]


def must_not_run(*_args, **_kwargs):
    raise AssertionError("hardware callback must not be invoked")


def boot(path, *, allow):
    return GuardianV1Application(
        configured_capabilities=set(),
        recovery_store=GuardianV1RecoveryStore(path),
        allow_restart_abort=allow,
    )


def cycle(app, power, *, roof=RoofState.OPEN):
    return app.evaluate_runtime_cycle(
        armed=False,
        roof_state=roof,
        asiair_state=AsiairState.ONLINE,
        commissioning=CommissioningStatus(results={}),
        configuration_fingerprint="test-fingerprint",
        execute_action=must_not_run,
        execute_safety_power=power,
    )


# --- The guarantee that makes this safe to deploy: off unless switched on ---


@pytest.mark.parametrize("session", ["IMAGING_PERMITTED", "WAITING_FOR_ROOF"])
def test_default_is_unchanged_recovery_block_and_no_hardware(tmp_path, session):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker(session))
    app = boot(path, allow=False)
    assert app.supervisor.restart_abort_pending is False
    assert app.supervisor.recovery_blocked
    cycle(app, must_not_run)  # would raise if anything tried to power off
    assert app.supervisor.incident is None
    assert app.supervisor.session_state is SessionState.DISARMED
    assert app.mode.monitor_only


# --- The new behaviour ---


@pytest.mark.parametrize(
    "session", ["IMAGING_PERMITTED", "WAITING_FOR_ROOF", "WAITING_FOR_PROTECTION"]
)
def test_restart_while_armed_powers_off_and_latches_aborted(tmp_path, session):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker(session))
    app = boot(path, allow=True)
    assert app.supervisor.restart_abort_pending is True

    power = FakePower()
    result = cycle(app, power)

    assert power.calls == [ALL_ROLES]  # ASIAIR, mount and accessories, one batch
    incident = app.supervisor.incident
    assert incident is not None
    assert incident.triggers == {ProtectionTrigger.RESTART_WHILE_ARMED}
    assert incident.unresolved_actions == []
    assert result.session.state is SessionState.ABORTED
    assert app.supervisor.session_state is SessionState.ABORTED
    assert app.supervisor.restart_abort_pending is False
    assert app.supervisor.recovery_blocked is False  # converted into the incident


def test_abort_happens_even_when_roof_is_open_and_asiair_online(tmp_path):
    """Operator's rule: armed + restart = abort, whatever the sky is doing."""
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    power = FakePower()
    cycle(app, power, roof=RoofState.OPEN)
    assert power.calls  # powered off despite OPEN roof


def test_incident_is_persisted_and_visible_to_the_morning_notice(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    cycle(app, FakePower())

    saved = GuardianV1RecoveryStore(path).read()
    assert saved["session_state"] == "ABORTED"
    assert saved["recovery_required"] is True
    assert saved["active_incident"]["triggers"] == ["RESTART_WHILE_ARMED"]
    assert recovery_notice(path) is not None  # operator will be told at login


def test_failed_power_off_is_retried_for_real_until_verified(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    power = FakePower(
        SafetyPowerResult.FAILED, SafetyPowerResult.FAILED, SafetyPowerResult.VERIFIED_OFF
    )

    cycle(app, power)
    assert app.supervisor.incident.unresolved_actions  # first attempt failed
    assert app.mode.hardware_execution_enabled  # retries stay real, not simulated

    cycle(app, power)  # retry 1: still failing
    assert app.supervisor.incident.unresolved_actions
    cycle(app, power)  # retry 2: verified
    assert app.supervisor.incident.unresolved_actions == []
    assert len(power.calls) == 3
    assert app.supervisor.session_state is SessionState.ABORTED  # stays latched


def test_abort_fires_once_not_every_cycle(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    power = FakePower()
    cycle(app, power)
    cycle(app, power)
    cycle(app, power)
    # Resolved on the first attempt, so later cycles must not power off again.
    assert len(power.calls) == 1


def test_operator_release_returns_hardware_to_disabled(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    cycle(app, FakePower())
    assert app.mode.hardware_execution_enabled

    assert app.acknowledge_abort()
    assert app.authorize_new_session()  # releases; never arms or powers on
    assert app.supervisor.incident is None
    assert app.supervisor.session_state is SessionState.DISARMED

    cycle(app, must_not_run)
    assert app.mode.monitor_only  # back to the safe default
    assert len(app.supervisor.incident_history) == 1


def test_release_is_refused_while_power_off_is_unverified(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    cycle(app, FakePower(SafetyPowerResult.FAILED))
    assert app.acknowledge_abort()
    assert not app.authorize_new_session()
    assert app.supervisor.incident is not None


def test_abort_survives_a_second_restart_without_firing_again(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    first = boot(path, allow=True)
    cycle(first, FakePower())

    second = boot(path, allow=True)
    assert second.supervisor.restart_abort_pending is False
    assert second.supervisor.incident is not None
    assert second.supervisor.session_state is SessionState.ABORTED


# --- States that must NOT trigger an abort ---


@pytest.mark.parametrize(
    "state",
    [
        marker("DISARMED", clean=True),
        marker("DISARMED", clean=False),  # watch-only monitor's normal footprint
    ],
)
def test_disarmed_restarts_never_abort(tmp_path, state):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(state)
    app = boot(path, allow=True)
    assert app.supervisor.restart_abort_pending is False
    cycle(app, must_not_run)
    assert app.supervisor.incident is None


def test_missing_recovery_file_does_not_abort(tmp_path):
    app = boot(tmp_path / "does-not-exist.json", allow=True)
    assert app.supervisor.restart_abort_pending is False
    assert app.supervisor.recovery_blocked  # existing fail-closed behaviour


# --- Misconfiguration must be loud, never a silent simulation ---


def test_pending_abort_without_a_power_executor_raises(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    with pytest.raises(RuntimeError, match="no safety-power executor"):
        app.evaluate_runtime_cycle(
            armed=False,
            roof_state=RoofState.OPEN,
            asiair_state=AsiairState.ONLINE,
            commissioning=CommissioningStatus(results={}),
            configuration_fingerprint="test-fingerprint",
            execute_action=must_not_run,
            execute_safety_power=None,
        )
    assert app.supervisor.incident is None
    assert app.mode.monitor_only


def test_protection_plan_is_the_standard_three_power_actions(tmp_path):
    path = tmp_path / "r.json"
    GuardianV1RecoveryStore(path).write(marker())
    app = boot(path, allow=True)
    cycle(app, FakePower())
    assert app.supervisor.incident.plan == [
        ProtectionAction.SAFETY_POWER_OFF_ASIAIR,
        ProtectionAction.SAFETY_POWER_OFF_MOUNT,
        ProtectionAction.SAFETY_POWER_OFF_ACCESSORIES,
    ]


# --- End to end: real recovery file, real Kasa routing, simulated outlets ---

from datetime import datetime, timezone  # noqa: E402

from modules.capability_model import REQUIRED_CAPABILITIES  # noqa: E402
from modules.commissioning import (  # noqa: E402
    REQUIRED_COMMISSIONING_CHECKS,
    CommissioningResult,
)
from modules.guardian_types import SafetyPowerState  # noqa: E402
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate  # noqa: E402
from modules.guardian_v1_starfront_kasa_integration import (  # noqa: E402
    compose_starfront_kasa_integration,
)
from modules.observatory_safety import ObservatorySafetyObservation  # noqa: E402
from modules.runtime_supervisor import RuntimeSupervisor  # noqa: E402

FINGERPRINT = "restart-abort-simulation"


class FakeKasa:
    """Simulated HS300: outlets 2, 3, 4 = ASIAIR, mount, accessories."""

    def __init__(self):
        self.states = {2: SafetyPowerState.ON, 3: SafetyPowerState.ON, 4: SafetyPowerState.ON}
        self.commands = []

    def check_outlet(self, number, alias):
        return (number, alias) in {(2, "ASIAIR"), (3, "Wave 150i"), (4, "Pegasus")}

    def get_outlet_state(self, number, alias):
        return self.states[number]

    def power_off_outlet(self, number, alias):
        self.commands.append(number)
        self.states[number] = SafetyPowerState.OFF
        return True


class FakeAsiair:
    def is_reachable(self):
        return True


class FakeRoof:
    def observe(self):
        return ObservatorySafetyObservation(
            state=RoofState.OPEN, observed_at=datetime.now(timezone.utc)
        )


def _commissioning():
    return CommissioningStatus(
        results={c: CommissioningResult.VERIFIED for c in REQUIRED_COMMISSIONING_CHECKS},
        configuration_fingerprint=FINGERPRINT,
    )


def _runtime(app, kasa):
    return compose_starfront_kasa_integration(
        application=app,
        asiair_host="example.invalid",
        alpaca_host="example.invalid",
        alpaca_port=443,
        alpaca_device_number=17,
        kasa_host="example.invalid",
        commissioning=_commissioning(),
        configuration_fingerprint=FINGERPRINT,
        kasa_transport=kasa,
        asiair_adapter=FakeAsiair(),
        observatory_adapter=FakeRoof(),
    )


def test_integrated_armed_session_then_restart_cuts_all_three_outlets(tmp_path):
    """The marker is produced by the real arm flow, not hand-written."""
    store = GuardianV1RecoveryStore(tmp_path / "r.json")
    store.write(RuntimeSupervisor().export_recovery_state())

    # Night 1: operator arms; Guardian reaches IMAGING_PERMITTED; nothing is cut.
    first = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store
    )
    kasa_before = FakeKasa()
    gate = GuardianV1ArmedGate(application=first, observation_runtime=_runtime(first, kasa_before))
    first.mode.enable_hardware_execution()  # isolated simulation only
    assert gate.arm()
    result = gate.cycle(now=datetime.now(timezone.utc))
    assert result.evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa_before.commands == []

    # Guardian dies here (crash, kill, reboot). A new process starts.
    second = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES),
        recovery_store=store,
        allow_restart_abort=True,
    )
    assert second.supervisor.restart_abort_pending
    assert second.mode.monitor_only  # starts with hardware off, as always

    kasa_after = FakeKasa()
    _runtime(second, kasa_after).run_cycle(armed=False, now=datetime.now(timezone.utc))

    assert sorted(kasa_after.commands) == [2, 3, 4]
    assert all(s is SafetyPowerState.OFF for s in kasa_after.states.values())
    assert second.supervisor.incident.triggers == {ProtectionTrigger.RESTART_WHILE_ARMED}
    assert store.read()["active_incident"]["triggers"] == ["RESTART_WHILE_ARMED"]


def test_integrated_restart_of_watch_only_process_never_touches_outlets(tmp_path):
    """Same crash, but the restarted process is the deployed watch-only kind."""
    store = GuardianV1RecoveryStore(tmp_path / "r.json")
    store.write(RuntimeSupervisor().export_recovery_state())
    first = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store
    )
    gate = GuardianV1ArmedGate(application=first, observation_runtime=_runtime(first, FakeKasa()))
    first.mode.enable_hardware_execution()
    assert gate.arm()
    gate.cycle(now=datetime.now(timezone.utc))

    watch_only = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store
    )  # allow_restart_abort defaults to False
    kasa = FakeKasa()
    _runtime(watch_only, kasa).run_cycle(armed=False, now=datetime.now(timezone.utc))
    assert kasa.commands == []
    assert watch_only.supervisor.incident is None
    assert watch_only.supervisor.recovery_blocked  # unchanged: operator inspects
