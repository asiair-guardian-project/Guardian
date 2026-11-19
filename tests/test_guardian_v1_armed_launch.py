"""Safety checks in the armed-monitor launcher. Simulated hardware only."""
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import guardian_v1
import guardian_v1_armed
from modules.commissioning import CommissioningCheck
from modules.guardian_types import SafetyPowerState
from modules.guardian_v1_armed_launch import (
    HARDWARE_TOKEN,
    build_armed_monitor,
    v06_running,
)
from modules.guardian_v1_commissioning_record import SCHEMA
from modules.guardian_v1_configuration_identity import semantic_fingerprint
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.runtime_supervisor import RuntimeSupervisor

INSTALLATION = {
    "asiair": {"ip_address": "192.0.2.10", "timeout_seconds": 2},
    "kasa": {"power_strip_ip": "192.0.2.20"},
    "roof": {"source": "alpaca", "alpaca_host": "alpaca.example.invalid",
             "alpaca_port": 443, "alpaca_device_number": 17,
             "alpaca_timeout_seconds": 5, "stale_after_seconds": None},
    "monitor": {"interval_seconds": 5},
}


class Kasa:
    def check_outlet(self, number, alias):
        return True

    def get_outlet_state(self, number, alias):
        return SafetyPowerState.ON

    def power_off_outlet(self, number, alias):
        return True


class Asiair:
    def is_reachable(self):
        return True


class Roof:
    def observe(self):
        raise OSError("not used in these tests")


@pytest.fixture
def env(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(INSTALLATION))
    recovery = tmp_path / "recovery.json"
    GuardianV1RecoveryStore(recovery).write(RuntimeSupervisor().export_recovery_state())
    root = tmp_path / "project"
    root.mkdir()
    return SimpleEnv(tmp_path, config, recovery, root)


class SimpleEnv:
    def __init__(self, tmp, config, recovery, root):
        self.tmp, self.config, self.recovery, self.root = tmp, config, recovery, root

    def args(self, *extra):
        return guardian_v1_armed.build_parser().parse_args([
            "--recovery-file", str(self.recovery),
            "--operator-socket", str(self.tmp / "s.sock"),
            "--asiair-host", "192.0.2.10",
            "--alpaca-host", "alpaca.example.invalid",
            "--alpaca-port", "443", "--alpaca-device", "17",
            "--installation-config", str(self.config),
            "--kasa-host", "192.0.2.20",
            *extra,
        ])

    def build(self, *extra):
        return build_armed_monitor(
            self.args(*extra), project_root=self.root, kasa_transport=Kasa(),
            asiair_adapter=Asiair(), observatory_adapter=Roof(),
            ups_adapter=None, send_alert=None,
        )

    def sign_off(self, **changes):
        record = {
            "schema": SCHEMA,
            "configuration_fingerprint": semantic_fingerprint(INSTALLATION),
            "approved_by": "Operator", "approved_at": "2026-11-02T12:00:00Z",
            "results": {c.name: "VERIFIED" for c in CommissioningCheck},
        }
        record.update(changes)
        path = self.tmp / "commissioning.json"
        path.write_text(json.dumps(record))
        path.chmod(0o600)
        return str(path)


# --- defaults are the safe ones -----------------------------------------------


def test_the_watch_only_entry_point_still_cannot_arm():
    source = (Path(__file__).resolve().parent.parent / "guardian_v1.py").read_text()
    for forbidden in ("armed_launch", "guardian_v1_armed", "enable_hardware", "YES_CUT_POWER"):
        assert forbidden not in source
    with pytest.raises(SystemExit):
        guardian_v1.build_parser().parse_args(["--armed"])
    with pytest.raises(SystemExit):
        guardian_v1.build_parser().parse_args(["--armed-monitor"])


def test_armed_entry_point_defaults_are_the_safe_ones():
    args = guardian_v1_armed.build_parser().parse_args([])
    assert args.enable_hardware_execution is None
    assert args.alert_level == "off"
    assert args.ups_unreadable_grace_seconds == 900.0
    assert args.ups_low_battery_percent == 35


def test_hardware_stays_off_without_the_token(env):
    runner, load, identity = env.build()
    assert runner.enable_hardware_execution is False
    assert runner.application.mode.hardware_execution_enabled is False
    assert runner.application.allow_restart_abort is True
    assert identity == semantic_fingerprint(INSTALLATION)


def test_the_exact_token_enables_hardware_for_the_runtime_only(env):
    runner, _, _ = env.build("--enable-hardware-execution", HARDWARE_TOKEN)
    assert runner.enable_hardware_execution is True
    # Still off at build time; the runtime switches it on when it starts.
    assert runner.application.mode.hardware_execution_enabled is False


@pytest.mark.parametrize("token", ["yes", "YES", "yes_cut_power", "TRUE", "1", "YES_CUT_POWER "])
def test_any_other_token_is_refused(env, token):
    with pytest.raises(SystemExit):
        env.build("--enable-hardware-execution", token)


# --- required settings ------------------------------------------------------------


@pytest.mark.parametrize("drop", ["--kasa-host", "--installation-config",
                                  "--recovery-file", "--operator-socket"])
def test_missing_required_setting_stops_the_launch(env, drop):
    args = env.args()
    setattr(args, drop.lstrip("-").replace("-", "_"), None)
    with pytest.raises(SystemExit):
        build_armed_monitor(args, project_root=env.root, kasa_transport=Kasa(),
                            asiair_adapter=Asiair(), observatory_adapter=Roof())


def test_kasa_host_must_match_the_installation(env):
    args = env.args()
    args.kasa_host = "192.0.2.99"
    with pytest.raises(SystemExit, match="kasa"):
        build_armed_monitor(args, project_root=env.root, kasa_transport=Kasa(),
                            asiair_adapter=Asiair(), observatory_adapter=Roof())


def test_monitor_settings_must_match_the_installation(env):
    args = env.args()
    args.asiair_host = "192.0.2.77"
    with pytest.raises(SystemExit):
        build_armed_monitor(args, project_root=env.root, kasa_transport=Kasa(),
                            asiair_adapter=Asiair(), observatory_adapter=Roof())


def test_a_pending_activation_journal_blocks_the_launch(env):
    journal = env.config.with_name("config.guardian-activation-journal.json")
    journal.write_text("{}")
    with pytest.raises(Exception):
        env.build()


# --- v0.6 interlock ----------------------------------------------------------------


def write_v06(root, **data):
    (root / "guardian_status.json").write_text(json.dumps(data))


def test_v06_detection(env):
    assert v06_running(env.root) is False  # no status file
    write_v06(env.root, running=True, pid=os.getpid())
    assert v06_running(env.root) is True
    write_v06(env.root, running=False, pid=os.getpid())
    assert v06_running(env.root) is False  # says it stopped
    write_v06(env.root, running=True, pid=2 ** 22 + 12345)
    assert v06_running(env.root) is False  # stale file, dead process
    (env.root / "guardian_status.json").write_text("not json")
    assert v06_running(env.root) is False


def test_hardware_cannot_be_enabled_while_v06_is_running(env):
    write_v06(env.root, running=True, pid=os.getpid())
    with pytest.raises(SystemExit, match="v0.6"):
        env.build("--enable-hardware-execution", HARDWARE_TOKEN)


def test_watch_only_launch_is_allowed_while_v06_runs(env):
    write_v06(env.root, running=True, pid=os.getpid())
    runner, _, _ = env.build()  # no hardware token: it only watches
    assert runner.enable_hardware_execution is False


# --- commissioning ---------------------------------------------------------------


def test_no_record_still_launches_but_arm_stays_refused(env):
    runner, load, _ = env.build("--enable-hardware-execution", HARDWARE_TOKEN)
    assert not load.usable
    runner.application.mode.enable_hardware_execution()
    assert runner.gate.arm() is False


def test_a_valid_record_lets_the_gate_accept_arm(env):
    runner, load, _ = env.build("--commissioning-record", env.sign_off(),
                                "--enable-hardware-execution", HARDWARE_TOKEN)
    assert load.usable and load.approved_by == "Operator"
    runner.application.mode.enable_hardware_execution()
    assert runner.gate.arm() is True


def test_a_record_for_another_configuration_does_not_commission(env):
    path = env.sign_off(configuration_fingerprint="0" * 64)
    runner, load, _ = env.build("--commissioning-record", path,
                                "--enable-hardware-execution", HARDWARE_TOKEN)
    assert not load.usable
    runner.application.mode.enable_hardware_execution()
    assert runner.gate.arm() is False


# --- settings reach the runtime ---------------------------------------------------


def test_alert_level_and_ups_settings_reach_the_runtime(env):
    runner, _, _ = env.build("--alert-level", "failure",
                             "--ups-unreadable-grace-seconds", "600",
                             "--ups-low-battery-percent", "40")
    assert runner.alerter.level.value == "failure"


def test_alert_level_choices_are_validated():
    with pytest.raises(SystemExit):
        guardian_v1_armed.build_parser().parse_args(["--alert-level", "sometimes"])


def test_asiair_needs_two_misses_by_default_and_the_setting_reaches_the_tracker(env):
    runner, _load, _identity = env.build()
    assert runner.observation_runtime._asiair_tracker._lost_after_misses == 2
    runner, _load, _identity = env.build("--asiair-lost-after-misses", "3")
    assert runner.observation_runtime._asiair_tracker._lost_after_misses == 3


def test_strip_is_checked_once_a_minute_by_default_and_the_setting_reaches_the_schedule(env):
    runner, _load, _identity = env.build()
    schedule = runner.observation_runtime._safety_power_schedule
    assert schedule is not None and schedule._interval == 60.0
    assert schedule._failures_to_degrade == 3 and schedule._retry == 4.0
    runner, _load, _identity = env.build("--strip-check-seconds", "120")
    assert runner.observation_runtime._safety_power_schedule._interval == 120.0
