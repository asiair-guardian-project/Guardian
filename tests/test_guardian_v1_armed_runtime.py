"""Armed-capable runtime, end to end, with simulated hardware only.

Real operator socket, real gate, real supervisor, real recovery file, real
Kasa shutdown path; the strip, ASIAIR, roof and UPS are fakes. Socket paths
are short (/tmp/...) because macOS limits unix socket paths to 104 chars.
"""
import json
import shutil
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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

FP = "armed-runtime-simulation"
ALIASES = {2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus"}


class FakeKasa:
    """Simulated strip with the one-connection batch path."""

    def __init__(self):
        self.states = {n: SafetyPowerState.ON for n in ALIASES}
        self.commands = []
        self.batch_commands = 0
        self.batch_reads = 0

    def check_outlet(self, number, alias):
        return ALIASES.get(number) == alias

    def get_outlet_state(self, number, alias):
        return self.states[number]

    def power_off_outlet(self, number, alias):
        self.commands.append(number)
        self.states[number] = SafetyPowerState.OFF
        return True

    def power_off_outlets(self, requests):
        self.batch_commands += 1
        for number, alias in requests:
            assert ALIASES[number] == alias and number != 1
            self.commands.append(number)
            self.states[number] = SafetyPowerState.OFF
        return {number: True for number, _ in requests}

    def get_outlet_states(self, requests):
        self.batch_reads += 1
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


class Outbox:
    def __init__(self):
        self.sent = []

    def __call__(self, level, message):
        self.sent.append((level, message))


@pytest.fixture
def workdir():
    directory = Path(tempfile.mkdtemp(prefix="ar", dir="/tmp"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def commissioned(ok=True):
    if not ok:
        return CommissioningStatus(results={})
    return CommissioningStatus(
        results={c: CommissioningResult.VERIFIED for c in REQUIRED_COMMISSIONING_CHECKS},
        configuration_fingerprint=FP,
    )


def build(workdir, *, kasa, roof, hardware=True, ok=True, level="all",
          outbox=None, sock="s.sock"):
    store = GuardianV1RecoveryStore(workdir / "recovery.json")
    if not store.path.exists():
        store.write(RuntimeSupervisor().export_recovery_state())
    app = GuardianV1Application(
        configured_capabilities=set(REQUIRED_CAPABILITIES),
        recovery_store=store,
        allow_restart_abort=True,
    )
    observation = compose_starfront_kasa_integration(
        application=app, asiair_host="x.invalid", alpaca_host="x.invalid",
        alpaca_port=443, alpaca_device_number=17, kasa_host="x.invalid",
        commissioning=commissioned(ok), configuration_fingerprint=FP,
        kasa_transport=kasa, asiair_adapter=Asiair(), observatory_adapter=roof,
    )
    gate = GuardianV1ArmedGate(application=app, observation_runtime=observation)
    runner = GuardianV1ArmedRuntime(
        application=app, gate=gate, observation_runtime=observation,
        socket_path=str(workdir / sock), interval_seconds=0.05,
        enable_hardware_execution=hardware,
        alerter=AbortAlerter(level, outbox, failure_confirm_cycles=2),
    )
    return app, runner


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
        if condition():
            return True
        time.sleep(0.02)
    return False


class Running:
    """Run the runtime on a thread and always stop it."""

    def __init__(self, runner):
        self.runner = runner
        self.thread = threading.Thread(target=runner.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        path = self.runner.socket.path
        assert wait_for(lambda: self._listening(path)), "runtime never started listening"
        return self

    @staticmethod
    def _listening(path):
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.5)
        try:
            probe.connect(str(path))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def __exit__(self, *exc):
        self.runner.stop()
        self.thread.join(5)
        assert not self.thread.is_alive()


def status(workdir, sock="s.sock"):
    return ask(workdir / sock, {"command": "STATUS"})


# --- the whole point: ARM, roof closes, power is cut ---------------------------


def test_arm_then_roof_closes_and_all_three_outlets_are_cut(workdir):
    kasa, roof, box = FakeKasa(), Roof(), Outbox()
    app, runner = build(workdir, kasa=kasa, roof=roof, outbox=box)

    with Running(runner):
        first = status(workdir)
        assert first["armed"] is False and first["hardware_execution_enabled"] is True

        reply = ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert reply["ok"] and reply["code"] == "ARMED"
        assert wait_for(lambda: status(workdir)["session"] == "IMAGING_PERMITTED")
        assert kasa.commands == []  # roof open: nothing is cut
        # Many cycles have run, yet the strip was only health-checked once
        # (60 s schedule, one connection for both required outlets).
        health_reads = kasa.batch_reads
        assert health_reads == 1

        roof.state = RoofState.CLOSED
        assert wait_for(lambda: status(workdir)["session"] == "ABORTED")

    assert sorted(kasa.commands) == [2, 3, 4]
    assert all(s is SafetyPowerState.OFF for s in kasa.states.values())
    # The cut itself: one connection to command, one fresh one to verify.
    assert kasa.batch_commands == 1 and kasa.batch_reads - health_reads == 1
    assert app.supervisor.incident.triggers == {ProtectionTrigger.ROOF_CLOSED}
    assert app.supervisor.incident.unresolved_actions == []
    assert any("ROOF_CLOSED" in message for _, message in box.sent)  # level "all"


def test_after_the_abort_arm_is_refused_until_the_operator_acknowledges(workdir):
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof)

    with Running(runner):
        ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert wait_for(lambda: status(workdir)["session"] == "IMAGING_PERMITTED")
        roof.state = RoofState.CLOSED
        assert wait_for(lambda: status(workdir)["session"] == "ABORTED")
        roof.state = RoofState.OPEN
        again = ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert again["ok"] is False
        assert status(workdir)["incident_active"] is True


# --- refusals --------------------------------------------------------------------


def test_without_the_hardware_setting_arm_is_refused_and_nothing_is_cut(workdir):
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof, hardware=False)

    with Running(runner):
        reply = ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert reply["ok"] is False
        assert status(workdir)["hardware_execution_enabled"] is False
        roof.state = RoofState.CLOSED
        time.sleep(0.3)

    assert kasa.commands == []
    assert app.mode.hardware_execution_enabled is False


def test_without_valid_commissioning_arm_is_refused_even_with_hardware_on(workdir):
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof, ok=False)

    with Running(runner):
        reply = ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert reply["ok"] is False and reply["code"] == "ARM_BLOCKED"
        assert status(workdir)["armed"] is False
        roof.state = RoofState.CLOSED
        time.sleep(0.3)

    assert kasa.commands == []


def test_constructor_refuses_unsafe_setups(workdir):
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof)

    app.mode.enable_hardware_execution()
    with pytest.raises(RuntimeError):
        GuardianV1ArmedRuntime(application=app, gate=runner.gate,
                               observation_runtime=runner.observation_runtime,
                               socket_path=str(workdir / "x.sock"))
    app.mode.disable_hardware_execution()

    other_app, _ = build(workdir, kasa=FakeKasa(), roof=Roof(), sock="o.sock")
    with pytest.raises(ValueError):
        GuardianV1ArmedRuntime(application=other_app, gate=runner.gate,
                               observation_runtime=runner.observation_runtime,
                               socket_path=str(workdir / "y.sock"))
    with pytest.raises(ValueError):
        GuardianV1ArmedRuntime(application=app, gate=runner.gate,
                               observation_runtime=runner.observation_runtime,
                               socket_path=str(workdir / "z.sock"), interval_seconds=0)
    storeless = SimpleNamespace(recovery_store=None,
                                mode=SimpleNamespace(hardware_execution_enabled=False))
    with pytest.raises(ValueError):
        GuardianV1ArmedRuntime(application=storeless, gate=SimpleNamespace(application=storeless),
                               observation_runtime=None, socket_path=str(workdir / "w.sock"))


# --- restart while armed (Patch 1) through the real runtime -----------------------


def test_restart_while_armed_cuts_power_on_the_first_cycle(workdir):
    kasa1, roof1 = FakeKasa(), Roof()
    app1, runner1 = build(workdir, kasa=kasa1, roof=roof1)

    with Running(runner1):
        ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert wait_for(lambda: status(workdir)["session"] == "IMAGING_PERMITTED")
    assert kasa1.commands == []  # stopped without an abort: the "crash"

    saved = json.loads((workdir / "recovery.json").read_text())
    assert saved["session_state"] == "IMAGING_PERMITTED"
    assert saved["shutdown_clean"] is False

    kasa2, roof2 = FakeKasa(), Roof()
    app2, runner2 = build(workdir, kasa=kasa2, roof=roof2)  # relaunch, same recovery file

    with Running(runner2):
        assert wait_for(lambda: status(workdir)["session"] == "ABORTED")

    assert sorted(kasa2.commands) == [2, 3, 4]
    assert app2.supervisor.incident.triggers == {ProtectionTrigger.RESTART_WHILE_ARMED}


# --- loop robustness -------------------------------------------------------------


class ExplodingObservation:
    _commissioning = commissioned()
    _configuration_fingerprint = FP
    calls = 0

    def run_cycle(self, *, armed, now):
        type(self).calls += 1
        raise RuntimeError("simulated programming fault")


def test_a_failing_cycle_is_counted_and_never_ends_the_loop(workdir):
    store = GuardianV1RecoveryStore(workdir / "recovery.json")
    store.write(RuntimeSupervisor().export_recovery_state())
    app = GuardianV1Application(configured_capabilities=set(REQUIRED_CAPABILITIES),
                                recovery_store=store)
    observation = ExplodingObservation()
    gate = GuardianV1ArmedGate(application=app, observation_runtime=observation)
    runner = GuardianV1ArmedRuntime(application=app, gate=gate,
                                    observation_runtime=observation,
                                    socket_path=str(workdir / "e.sock"),
                                    interval_seconds=0.01)

    assert runner.run(cycles=4) == 4
    assert runner.cycle_errors == 4
    assert not (workdir / "e.sock").exists()  # socket closed on the way out


def test_a_broken_alerter_never_stops_protection(workdir):
    kasa, roof = FakeKasa(), Roof()

    def broken(level, message):
        raise OSError("no internet")

    app, runner = build(workdir, kasa=kasa, roof=roof, outbox=broken)

    with Running(runner):
        ask(workdir / "s.sock", {"command": "ARM", "confirmed": True})
        assert wait_for(lambda: status(workdir)["session"] == "IMAGING_PERMITTED")
        roof.state = RoofState.CLOSED
        assert wait_for(lambda: status(workdir)["session"] == "ABORTED")

    assert sorted(kasa.commands) == [2, 3, 4]


def test_a_stop_requested_before_the_loop_starts_is_not_lost(workdir):
    kasa, roof = FakeKasa(), Roof()
    app, runner = build(workdir, kasa=kasa, roof=roof)

    runner.stop()  # e.g. SIGTERM arriving while the monitor is still starting
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(runner.run()), daemon=True)
    thread.start()
    thread.join(3)
    assert not thread.is_alive(), "run() ignored a stop requested before it started"
    assert outcome == [0]  # returned at once instead of running forever
    assert not (workdir / "s.sock").exists()  # and still closes its socket
    assert app.mode.hardware_execution_enabled is False  # never got as far as enabling
