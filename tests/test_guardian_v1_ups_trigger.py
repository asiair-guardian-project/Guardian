"""UPS low-battery abort for Guardian 1.0.

Simulated UPS and simulated Kasa outlets only. No network, no hardware, no
real `pmset` call.
"""
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from modules.asiair_state import AsiairStateTracker
from modules.capability_model import REQUIRED_CAPABILITIES
from modules.capability_registry import CapabilityRegistry
from modules.commissioning import (
    REQUIRED_COMMISSIONING_CHECKS,
    CommissioningResult,
    CommissioningStatus,
)
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    ProtectionTrigger,
    RoofState,
    SafetyPowerState,
    SessionState,
)
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_observation_cycle import run_observation_cycle
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_starfront_kasa_integration import (
    compose_starfront_kasa_integration,
)
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.protection_evaluator import evaluate_protection_triggers
from modules.runtime_supervisor import RuntimeSupervisor
from modules.ups_adapter import (
    PmsetUpsAdapter,
    UpsReadError,
    UpsReading,
    parse_pmset_batt,
    read_ups_low_battery,
    ups_is_low,
)

AC = "Now drawing from 'AC Power'\n -CP1350PFCLCDa (id=1234)\t100%; AC attached; not charging present: true\n"
UPS_82 = "Now drawing from 'UPS Power'\n -SomeOtherUPS (id=99)\t82%; discharging; 31:00 remaining present: true\n"
UPS_35 = "Now drawing from 'UPS Power'\n -CP1350PFCLCDa (id=1234)\t35%; discharging; 12:00 remaining present: true\n"
UPS_NO_PCT = "Now drawing from 'UPS Power'\n -CP1350PFCLCDa (id=1234)\tdischarging present: true\n"


# --- parsing -----------------------------------------------------------------


def test_parse_mains():
    assert parse_pmset_batt(AC) == UpsReading(on_battery=False, battery_percent=100)


def test_parse_on_battery_any_ups_model():
    assert parse_pmset_batt(UPS_82) == UpsReading(on_battery=True, battery_percent=82)


def test_parse_on_battery_without_percent():
    assert parse_pmset_batt(UPS_NO_PCT) == UpsReading(on_battery=True, battery_percent=None)


@pytest.mark.parametrize("bad", ["", None, "garbage", "Now drawing from 'Mystery Power'\n 50%"])
def test_parse_rejects_unknown_power_source(bad):
    with pytest.raises(UpsReadError):
        parse_pmset_batt(bad)


def test_parse_rejects_implausible_percent():
    with pytest.raises(UpsReadError):
        parse_pmset_batt("Now drawing from 'UPS Power'\n 250%; discharging")


# --- policy ------------------------------------------------------------------


@pytest.mark.parametrize(
    "on_battery, percent, expected",
    [
        (False, 100, False),
        (False, 5, False),  # on mains is never "low", even at a low charge
        (True, 82, False),
        (True, 36, False),
        (True, 35, True),  # threshold is inclusive, as in v0.6
        (True, 20, True),
        (True, None, True),  # on battery and unreadable: fail conservative
    ],
)
def test_low_battery_policy(on_battery, percent, expected):
    assert ups_is_low(UpsReading(on_battery, percent), 35) is expected


def test_threshold_is_configurable():
    assert ups_is_low(UpsReading(True, 50), 50) is True
    assert ups_is_low(UpsReading(True, 51), 50) is False


# --- adapter -----------------------------------------------------------------


def _runner(stdout="", returncode=0, raises=None):
    def run(*args, **kwargs):
        if raises:
            raise raises
        return SimpleNamespace(stdout=stdout, returncode=returncode)

    return run


def test_adapter_reads_through_pmset():
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(stdout=UPS_35, returncode=0)

    reading = PmsetUpsAdapter(runner=run).read()
    assert seen["cmd"] == ["pmset", "-g", "batt"]
    assert reading == UpsReading(True, 35)


@pytest.mark.parametrize(
    "runner",
    [
        _runner(raises=FileNotFoundError("pmset")),
        _runner(raises=subprocess.TimeoutExpired("pmset", 5)),
        _runner(stdout="", returncode=1),
        _runner(stdout="no power info here", returncode=0),
    ],
)
def test_adapter_failures_become_ups_read_error(runner):
    with pytest.raises(UpsReadError):
        PmsetUpsAdapter(runner=runner).read()


def test_unreadable_ups_is_not_low_and_never_raises():
    assert read_ups_low_battery(PmsetUpsAdapter(runner=_runner(raises=OSError("boom")))) is False


def test_no_adapter_means_never_low():
    assert read_ups_low_battery(None) is False


def test_helper_reports_low_only_when_on_battery_and_low():
    assert read_ups_low_battery(PmsetUpsAdapter(runner=_runner(UPS_35))) is True
    assert read_ups_low_battery(PmsetUpsAdapter(runner=_runner(UPS_82))) is False
    assert read_ups_low_battery(PmsetUpsAdapter(runner=_runner(AC))) is False


# --- trigger evaluation ------------------------------------------------------

OK = [CapabilityStatus.AVAILABLE]


def _triggers(session=SessionState.IMAGING_PERMITTED, roof=RoofState.OPEN, ups=False):
    return evaluate_protection_triggers(
        session_state=session,
        roof_state=roof,
        asiair_state=AsiairState.ONLINE,
        required_capability_statuses=OK,
        ups_low_battery=ups,
    )


def test_ups_low_during_imaging_is_a_trigger():
    assert _triggers(ups=True) == {ProtectionTrigger.UPS_LOW_BATTERY}


def test_ups_low_alone_is_not_a_trigger_before_imaging_or_when_not_low():
    assert _triggers(ups=False) == set()
    for state in (
        SessionState.DISARMED,
        SessionState.WAITING_FOR_ROOF,
        SessionState.WAITING_FOR_PROTECTION,
    ):
        assert _triggers(session=state, ups=True) == set()


def test_ups_and_roof_can_trigger_together():
    assert _triggers(roof=RoofState.CLOSED, ups=True) == {
        ProtectionTrigger.ROOF_CLOSED,
        ProtectionTrigger.UPS_LOW_BATTERY,
    }


def test_default_is_backward_compatible():
    # Callers that predate the UPS flag must behave exactly as before.
    assert evaluate_protection_triggers(
        session_state=SessionState.IMAGING_PERMITTED,
        roof_state=RoofState.OPEN,
        asiair_state=AsiairState.ONLINE,
        required_capability_statuses=OK,
    ) == set()


# --- observation cycle -------------------------------------------------------


class _Asiair:
    def is_reachable(self):
        return True


class _Roof:
    def observe(self):
        return ObservatorySafetyObservation(
            state=RoofState.OPEN, observed_at=datetime.now(timezone.utc)
        )


class _Ups:
    def __init__(self, reading):
        self.reading = reading

    def read(self):
        return self.reading


def _cycle(**kwargs):
    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
        }
    )
    return run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=_Asiair(),
        observatory_adapter=_Roof(),
        now=datetime.now(timezone.utc),
        roof_max_age_seconds=30,
        **kwargs,
    ).observation


def test_observation_defaults_to_no_ups():
    assert _cycle().ups_low_battery is False


def test_observation_reports_low_ups():
    assert _cycle(ups_adapter=_Ups(UpsReading(True, 30))).ups_low_battery is True
    assert _cycle(ups_adapter=_Ups(UpsReading(True, 90))).ups_low_battery is False
    assert _cycle(ups_adapter=_Ups(UpsReading(False, 3))).ups_low_battery is False


def test_observation_honours_custom_threshold():
    reading = _Ups(UpsReading(True, 50))
    assert _cycle(ups_adapter=reading, ups_low_battery_percent=50).ups_low_battery is True
    assert _cycle(ups_adapter=reading, ups_low_battery_percent=40).ups_low_battery is False


# --- end to end: armed session, UPS drains, outlets get cut -------------------

FINGERPRINT = "ups-simulation"


class FakeKasa:
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


class ScriptedUps:
    def __init__(self, reading):
        self.reading = reading
        self.fail = False

    def read(self):
        if self.fail:
            raise UpsReadError("simulated USB dropout")
        return self.reading


def _armed_gate(tmp_path, ups, **runtime_kwargs):
    store = GuardianV1RecoveryStore(tmp_path / "r.json")
    store.write(RuntimeSupervisor().export_recovery_state())
    app = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES), recovery_store=store
    )
    kasa = FakeKasa()
    runtime = compose_starfront_kasa_integration(
        application=app,
        asiair_host="example.invalid",
        alpaca_host="example.invalid",
        alpaca_port=443,
        alpaca_device_number=17,
        kasa_host="example.invalid",
        commissioning=CommissioningStatus(
            results={c: CommissioningResult.VERIFIED for c in REQUIRED_COMMISSIONING_CHECKS},
            configuration_fingerprint=FINGERPRINT,
        ),
        configuration_fingerprint=FINGERPRINT,
        kasa_transport=kasa,
        asiair_adapter=_Asiair(),
        observatory_adapter=_Roof(),
        ups_adapter=ups,
        ups_low_battery_percent=35,
        **runtime_kwargs,
    )
    gate = GuardianV1ArmedGate(application=app, observation_runtime=runtime)
    app.mode.enable_hardware_execution()  # isolated simulation only
    assert gate.arm()
    return gate, app, kasa, store


def _now():
    return datetime.now(timezone.utc)


def test_ups_drains_mid_session_and_all_three_outlets_are_cut(tmp_path):
    ups = ScriptedUps(UpsReading(False, 100))  # healthy mains
    gate, app, kasa, store = _armed_gate(tmp_path, ups)

    assert gate.cycle(now=_now()).evaluation.session.state is SessionState.IMAGING_PERMITTED

    ups.reading = UpsReading(True, 82)  # mains fails, plenty of battery
    assert gate.cycle(now=_now()).evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []

    ups.reading = UpsReading(True, 35)  # reaches the threshold
    assert gate.cycle(now=_now()).evaluation.session.state is SessionState.ABORTED
    assert sorted(kasa.commands) == [2, 3, 4]
    assert app.supervisor.incident.triggers == {ProtectionTrigger.UPS_LOW_BATTERY}
    assert store.read()["active_incident"]["triggers"] == ["UPS_LOW_BATTERY"]
    assert app.supervisor.incident.unresolved_actions == []


def test_unreadable_ups_does_not_abort_a_healthy_session(tmp_path):
    ups = ScriptedUps(UpsReading(False, 100))
    gate, app, kasa, _ = _armed_gate(tmp_path, ups)
    gate.cycle(now=_now())
    ups.fail = True
    result = gate.cycle(now=_now())
    assert result.evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []


def test_ups_already_low_at_arming_is_caught_on_the_next_cycle(tmp_path):
    """The arming cycle evaluates no triggers (existing behaviour), so a UPS
    that is already low is acted on one cycle later."""
    gate, app, kasa, _ = _armed_gate(tmp_path, ScriptedUps(UpsReading(True, 10)))

    first = gate.cycle(now=_now())
    assert first.evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []

    second = gate.cycle(now=_now())
    assert second.evaluation.session.state is SessionState.ABORTED
    assert sorted(kasa.commands) == [2, 3, 4]


def test_without_a_ups_adapter_nothing_changes(tmp_path):
    gate, app, kasa, _ = _armed_gate(tmp_path, None)
    for _ in range(3):
        assert gate.cycle(now=_now()).evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []


# --- unreadable UPS: aborts only after the grace period ----------------------


def test_ups_unreadable_past_the_grace_period_aborts_and_cuts_power(tmp_path):
    import time

    ups = ScriptedUps(UpsReading(False, 100))
    gate, app, kasa, store = _armed_gate(
        tmp_path, ups, ups_unreadable_grace_seconds=0.05
    )
    gate.cycle(now=_now())  # arming cycle
    ups.fail = True

    # Just became unreadable: a short outage is tolerated.
    assert gate.cycle(now=_now()).evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []

    time.sleep(0.1)  # still unreadable past the (tiny, test-only) grace
    assert gate.cycle(now=_now()).evaluation.session.state is SessionState.ABORTED
    assert sorted(kasa.commands) == [2, 3, 4]
    assert app.supervisor.incident.triggers == {ProtectionTrigger.UPS_LOW_BATTERY}


def test_ups_that_comes_back_before_the_grace_period_resets_the_clock(tmp_path):
    import time

    ups = ScriptedUps(UpsReading(False, 100))
    gate, app, kasa, _ = _armed_gate(
        tmp_path, ups, ups_unreadable_grace_seconds=0.15
    )
    gate.cycle(now=_now())
    ups.fail = True
    gate.cycle(now=_now())
    time.sleep(0.1)
    ups.fail = False  # recovers in time
    gate.cycle(now=_now())
    ups.fail = True
    gate.cycle(now=_now())  # a NEW outage: the clock restarted
    time.sleep(0.1)
    assert gate.cycle(now=_now()).evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert kasa.commands == []
