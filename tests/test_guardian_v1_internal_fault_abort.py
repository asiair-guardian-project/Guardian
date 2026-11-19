"""If Guardian itself fails while armed, protect the gear first.

Simulated strip, roof and ASIAIR; real gate, supervisor, recovery file and
operator socket. The 'fault' is an exception escaping a cycle (probe errors
never do: they are turned into 'unavailable' statuses before this point).
"""
import json
import shutil
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from modules.abort_alerter import AbortAlerter
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
from modules.guardian_v1_armed_runtime import GuardianV1ArmedRuntime
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_starfront_kasa_integration import (
    compose_starfront_kasa_integration,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.runtime_supervisor import RuntimeSupervisor

FP = "internal-fault-simulation"
ALIASES = {2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus"}


class FakeKasa:
    def __init__(self):
        self.states = {n: SafetyPowerState.ON for n in ALIASES}
        self.commands = []
        self.down = False

    def check_outlet(self, number, alias):
        return ALIASES.get(number) == alias

    def get_outlet_state(self, number, alias):
        return self.states[number]

    def power_off_outlet(self, number, alias):
        return True

    def power_off_outlets(self, requests):
        if self.down:
            raise OSError("strip unreachable")
        for number, _ in requests:
            self.commands.append(number)
            self.states[number] = SafetyPowerState.OFF
        return {number: True for number, _ in requests}

    def get_outlet_states(self, requests):
        if self.down:
            raise OSError("strip unreachable")
        return {number: self.states[number] for number, _ in requests}


class Asiair:
    def is_reachable(self):
        return True


class Roof:
    def __init__(self):
        self.state = RoofState.OPEN

    def observe(self):
        return ObservatorySafetyObservation(
            state=self.state, observed_at=datetime.now(timezone.utc)
        )


class Chaos:
    """Wraps the real observation runtime; raises on demand."""

    def __init__(self, inner):
        self._inner = inner
        self.fault = False

    def run_cycle(self, *, armed, now):
        if self.fault:
            raise RuntimeError("simulated Guardian fault")
        return self._inner.run_cycle(armed=armed, now=now)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture
def workdir():
    directory = Path(tempfile.mkdtemp(prefix="if", dir="/tmp"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def build(workdir, kasa=None, hardware=True):
    kasa = kasa or FakeKasa()
    store = GuardianV1RecoveryStore(workdir / "recovery.json")
    if not store.path.exists():
        store.write(RuntimeSupervisor().export_recovery_state())
    app = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES),
        recovery_store=store, allow_restart_abort=True,
    )
    observation = compose_starfront_kasa_integration(
        application=app, asiair_host="x.invalid", alpaca_host="x.invalid",
        alpaca_port=443, alpaca_device_number=17, kasa_host="x.invalid",
        commissioning=CommissioningStatus(
            results={c: CommissioningResult.VERIFIED for c in REQUIRED_COMMISSIONING_CHECKS},
            configuration_fingerprint=FP),
        configuration_fingerprint=FP, kasa_transport=kasa,
        asiair_adapter=Asiair(), observatory_adapter=Roof(),
    )
    chaos = Chaos(observation)
    gate = GuardianV1ArmedGate(application=app, observation_runtime=chaos)
    if hardware:
        app.mode.enable_hardware_execution()
    return app, gate, chaos, kasa


def active_session(workdir, **kw):
    app, gate, chaos, kasa = build(workdir, **kw)
    assert gate.arm()
    gate.cycle()  # the arming cycle: session becomes IMAGING_PERMITTED
    assert app.supervisor.session_state is SessionState.IMAGING_PERMITTED
    return app, gate, chaos, kasa


def now():
    return datetime.now(timezone.utc)


# --- the decision: protect the gear first -------------------------------------


def test_fault_during_an_armed_session_cuts_all_three_outlets(workdir):
    app, gate, chaos, kasa = active_session(workdir)
    chaos.fault = True

    with pytest.raises(RuntimeError, match="simulated Guardian fault"):
        gate.cycle()  # the original error still surfaces

    assert sorted(kasa.commands) == [2, 3, 4]
    assert all(s is SafetyPowerState.OFF for s in kasa.states.values())
    assert app.supervisor.session_state is SessionState.ABORTED
    assert app.supervisor.incident.triggers == {ProtectionTrigger.INTERNAL_FAULT}
    assert app.supervisor.incident.unresolved_actions == []
    assert gate.armed is False
    assert app.mode.hardware_execution_enabled is True  # retries stay real

    saved = json.loads((workdir / "recovery.json").read_text())
    assert saved["active_incident"]["triggers"] == ["INTERNAL_FAULT"]


def test_fault_during_the_arming_cycle_also_cuts_power(workdir):
    app, gate, chaos, kasa = build(workdir)
    assert gate.arm()
    chaos.fault = True  # the very first armed cycle fails

    with pytest.raises(RuntimeError):
        gate.cycle()

    assert sorted(kasa.commands) == [2, 3, 4]
    assert app.supervisor.incident.triggers == {ProtectionTrigger.INTERNAL_FAULT}


def test_fault_after_disarm_does_not_cut_because_disarm_ended_the_session(workdir):
    # Patch 32 (operator decision, 2026-11-14): DISARM hands the rig back to the operator and ends
    # the session, so nothing is protected until they ARM again. (Before, DISARM left the session
    # IMAGING_PERMITTED: ARM stayed refused and a restart looked like a restart while armed.)
    app, gate, chaos, kasa = active_session(workdir)
    assert gate.disarm() is True
    chaos.fault = True

    with pytest.raises(RuntimeError):
        gate.cycle()

    assert kasa.commands == []
    assert app.supervisor.incident is None


def test_fault_when_nothing_is_armed_does_not_cut_power(workdir):
    app, gate, chaos, kasa = build(workdir)
    chaos.fault = True

    with pytest.raises(RuntimeError):
        gate.cycle()

    assert kasa.commands == []
    assert app.supervisor.incident is None
    assert app.mode.hardware_execution_enabled is False  # existing fail-closed behaviour


def test_fault_in_a_watch_only_process_cannot_cut_power(workdir):
    app, gate, chaos, kasa = build(workdir, hardware=False)
    chaos.fault = True

    with pytest.raises(RuntimeError):
        gate.cycle()

    assert kasa.commands == []
    assert app.supervisor.incident is None


# --- retries while the fault persists --------------------------------------------


def test_unreachable_strip_at_fault_time_is_retried_on_later_faults(workdir):
    kasa = FakeKasa()
    app, gate, chaos, _ = active_session(workdir, kasa=kasa)
    kasa.down = True
    chaos.fault = True

    with pytest.raises(RuntimeError):
        gate.cycle()
    assert kasa.commands == []
    assert app.supervisor.incident.unresolved_actions  # could not be cut yet

    with pytest.raises(RuntimeError):
        gate.cycle()  # still failing, still down
    assert app.supervisor.incident.unresolved_actions

    kasa.down = False  # strip comes back; the fault is still there
    with pytest.raises(RuntimeError):
        gate.cycle()

    assert sorted(kasa.commands) == [2, 3, 4]
    assert app.supervisor.incident.unresolved_actions == []


def test_a_resolved_incident_is_not_cut_again_by_repeated_faults(workdir):
    app, gate, chaos, kasa = active_session(workdir)
    chaos.fault = True
    for _ in range(4):
        with pytest.raises(RuntimeError):
            gate.cycle()
    assert sorted(kasa.commands) == [2, 3, 4]  # exactly one cut, never repeated
    assert len(app.supervisor.incident.triggers) == 1


def test_a_normal_cycle_after_the_fault_keeps_retrying_and_stays_aborted(workdir):
    kasa = FakeKasa()
    app, gate, chaos, _ = active_session(workdir, kasa=kasa)
    kasa.down = True
    chaos.fault = True
    with pytest.raises(RuntimeError):
        gate.cycle()
    chaos.fault = False  # the fault clears
    kasa.down = False

    gate.cycle()  # a healthy cycle: retries through the normal path

    assert sorted(kasa.commands) == [2, 3, 4]
    assert app.supervisor.session_state is SessionState.ABORTED


# --- guards and durability ---------------------------------------------------------


def test_with_hardware_off_mid_session_no_incident_is_invented(workdir):
    # Hardware execution can only be switched off by something other than the
    # launch setting. If it is off, Guardian cannot cut power, so it must not
    # latch an "aborted" incident whose power-off could never be verified.
    app, gate, chaos, kasa = active_session(workdir)
    gate.disarm()
    app.mode.disable_hardware_execution()
    chaos.fault = True

    with pytest.raises(RuntimeError):
        gate.cycle()

    assert kasa.commands == []
    assert app.supervisor.incident is None


def test_the_application_saves_the_fault_incident_by_itself(workdir):
    app, gate, chaos, kasa = active_session(workdir)

    incident = app.abort_for_internal_fault(
        armed=True,
        execute_action=chaos._execute_action,
        execute_safety_power=chaos._execute_safety_power,
    )

    assert incident.triggers == {ProtectionTrigger.INTERNAL_FAULT}
    saved = json.loads((workdir / "recovery.json").read_text())
    assert saved["active_incident"]["triggers"] == ["INTERNAL_FAULT"]
    assert sorted(kasa.commands) == [2, 3, 4]


def test_the_application_saves_the_result_of_a_retry(workdir):
    kasa = FakeKasa()
    app, gate, chaos, _ = active_session(workdir, kasa=kasa)
    kasa.down = True
    app.abort_for_internal_fault(
        armed=True,
        execute_action=chaos._execute_action,
        execute_safety_power=chaos._execute_safety_power,
    )
    assert app.supervisor.incident.unresolved_actions

    kasa.down = False
    assert app.retry_protection(
        execute_action=chaos._execute_action,
        execute_safety_power=chaos._execute_safety_power,
    ) is True

    app2, _, _, _ = build(workdir)  # reload what was written to disk
    assert app2.supervisor.incident.unresolved_actions == []
    assert app.retry_protection(  # nothing left to retry
        execute_action=chaos._execute_action,
        execute_safety_power=chaos._execute_safety_power,
    ) is False


# --- operator flow and restart ------------------------------------------------------


def test_restart_after_a_fault_abort_restores_it_without_cutting_again(workdir):
    app, gate, chaos, kasa = active_session(workdir)
    chaos.fault = True
    with pytest.raises(RuntimeError):
        gate.cycle()
    assert sorted(kasa.commands) == [2, 3, 4]

    app2, gate2, chaos2, kasa2 = build(workdir)  # relaunch on the same recovery file

    assert app2.supervisor.session_state is SessionState.ABORTED
    assert app2.supervisor.incident.triggers == {ProtectionTrigger.INTERNAL_FAULT}
    gate2.cycle()
    assert kasa2.commands == []  # already shut down: nothing more to do
    assert gate2.arm() is False  # and ARM stays refused until acknowledged


def test_operator_can_acknowledge_and_release_a_fault_abort(workdir):
    app, gate, chaos, kasa = active_session(workdir)
    chaos.fault = True
    with pytest.raises(RuntimeError):
        gate.cycle()
    chaos.fault = False

    assert gate.arm() is False  # locked until the operator acts
    assert app.acknowledge_abort() is True
    assert app.authorize_new_session() is True
    assert app.supervisor.incident is None
    assert app.supervisor.session_state is SessionState.DISARMED


# --- through the live runtime ----------------------------------------------------------


def ask(path, payload):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(3)
    client.connect(str(path))
    client.sendall(json.dumps(payload).encode() + b"\n")
    data = b""
    while b"\n" not in data:
        data += client.recv(4096)
    client.close()
    return json.loads(data.split(b"\n")[0])


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if condition():
                return True
        except OSError:
            pass
        time.sleep(0.02)
    return False


def test_live_runtime_cuts_power_on_a_fault_keeps_running_and_alerts(workdir):
    app, gate, chaos, kasa = build(workdir, hardware=False)
    sent = []
    runner = GuardianV1ArmedRuntime(
        application=app, gate=gate, observation_runtime=chaos,
        socket_path=str(workdir / "s.sock"), interval_seconds=0.05,
        enable_hardware_execution=True,
        alerter=AbortAlerter("all", lambda level, message: sent.append(message)),
    )
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    sock = workdir / "s.sock"
    try:
        assert wait_for(lambda: ask(sock, {"command": "STATUS"})["ok"])
        assert ask(sock, {"command": "ARM", "confirmed": True})["code"] == "ARMED"
        assert wait_for(lambda: ask(sock, {"command": "STATUS"})["session"] == "IMAGING_PERMITTED")

        chaos.fault = True  # Guardian malfunctions mid-session

        assert wait_for(lambda: ask(sock, {"command": "STATUS"})["session"] == "ABORTED")
        time.sleep(0.3)
        assert thread.is_alive()  # the loop survived the fault
    finally:
        runner.stop()
        thread.join(5)

    assert sorted(kasa.commands) == [2, 3, 4]
    assert runner.cycle_errors >= 1
    assert app.supervisor.incident.triggers == {ProtectionTrigger.INTERNAL_FAULT}
    assert any("INTERNAL_FAULT" in message for message in sent)
