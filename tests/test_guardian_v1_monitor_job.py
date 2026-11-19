"""The watching-only monitor job for a new operator (never cuts power, never overwrites, matches the live file)."""
import os
import plistlib
import re
import stat
from pathlib import Path

import pytest

import guardian_v1_install_monitor as cli
from modules import guardian_v1_stage_b as sb
from modules.guardian_v1_monitor_job import MonitorJobError, build_plist, check_installation, write_plist

HOME = "/Users/YOUR_USER"
SUPPORT = f"{HOME}/Library/Application Support/GuardianV1"
PROJECT = f"{HOME}/ObservatorySupervisor"
INSTALL = {"asiair": {"ip_address": "192.168.1.20", "timeout_seconds": 2},
           "roof": {"source": "alpaca", "alpaca_host": "alpaca-api.tx.starfront.space", "alpaca_port": 443,
                    "alpaca_device_number": 17, "alpaca_timeout_seconds": 5, "stale_after_seconds": 30},
           "kasa": {"power_strip_ip": "192.168.1.30"}, "monitor": {"interval_seconds": 5}}

# The live Starfront job as printed by plutil on 2026-11-19, WITHOUT the two Stage B hardware arguments.
LIVE_WATCHING_ONLY = {
    "KeepAlive": {"SuccessfulExit": False}, "Label": "org.guardian.v1.monitor",
    "ProgramArguments": [
        f"{PROJECT}/.venv/bin/python", f"{PROJECT}/guardian_v1_armed.py",
        "--recovery-file", f"{SUPPORT}/recovery.json", "--operator-socket", f"{SUPPORT}/operator.sock",
        "--asiair-host", "192.168.1.20", "--alpaca-host", "alpaca-api.tx.starfront.space",
        "--alpaca-port", "443", "--alpaca-device", "17", "--kasa-host", "192.168.1.30",
        "--cycle-seconds", "5", "--installation-config", f"{PROJECT}/config/config.yaml",
        "--commissioning-record", f"{SUPPORT}/commissioning.json",
        "--ups-low-battery-percent", "35", "--ups-unreadable-grace-seconds", "900", "--alert-level", "off"],
    "RunAtLoad": True, "StandardErrorPath": f"{SUPPORT}/monitor_stderr.log",
    "StandardOutPath": f"{SUPPORT}/monitor_stdout.log", "ThrottleInterval": 10, "WorkingDirectory": PROJECT}


def make(installation=INSTALL, **kw):
    kw.setdefault("project_dir", PROJECT)
    kw.setdefault("python", f"{PROJECT}/.venv/bin/python")
    kw.setdefault("config_path", f"{PROJECT}/config/config.yaml")
    kw.setdefault("support_dir", SUPPORT)
    return build_plist(installation, **kw)


def test_it_reproduces_the_live_starfront_job_exactly():
    assert make() == LIVE_WATCHING_ONLY


def test_the_job_can_never_cut_power():
    plist = make()
    assert sb.HARDWARE_FLAG not in plist["ProgramArguments"] and not sb.hardware_enabled_in(plist)
    assert "YES_CUT_POWER" not in plist["ProgramArguments"]


def test_stage_b_accepts_the_generated_job_and_can_round_trip_it():
    plist = make()
    sb.check_monitor_plist(plist)
    with_hw = sb.with_hardware(plist)
    assert sb.hardware_enabled_in(with_hw) and sb.without_hardware(with_hw) == plist


@pytest.mark.parametrize("change", [
    lambda i: i["asiair"].update(ip_address="not an address"),
    lambda i: i["roof"].update(alpaca_port=0),
    lambda i: i["roof"].update(alpaca_device_number=999),
    lambda i: i["kasa"].update(power_strip_ip=""),
    lambda i: i.pop("kasa"),
    lambda i: i.update(power={"type": "nonsense"}),
])
def test_a_bad_installation_is_refused(change):
    import copy
    bad = copy.deepcopy(INSTALL)
    change(bad)
    with pytest.raises(MonitorJobError):
        make(bad)


def test_a_valid_power_section_is_accepted():
    ok = {**INSTALL, "power": {"type": "digital_loggers_rest", "host_outlet": {"number": 1, "alias": "Mac"},
                               "targets": {"asiair": {"number": 2, "alias": "A"}, "mount": {"number": 3, "alias": "M"},
                                           "accessories": {"number": 4, "alias": "D"}}}}
    assert check_installation(ok)["kasa_host"] == "192.168.1.30"


def test_relative_paths_and_the_candidate_file_are_refused():
    with pytest.raises(MonitorJobError):
        make(project_dir="ObservatorySupervisor")
    with pytest.raises(MonitorJobError):
        make(config_path=f"{PROJECT}/config.guardian-candidate.yaml")
    with pytest.raises(MonitorJobError):
        make(alert_level="loud")


def test_write_creates_a_new_file_with_a_private_support_folder_and_never_overwrites(tmp_path):
    target, support = tmp_path / "LaunchAgents" / "org.guardian.v1.monitor.plist", tmp_path / "support"
    write_plist(make(support_dir=str(support)), target, support)
    assert plistlib.loads(target.read_bytes())["Label"] == "org.guardian.v1.monitor"
    assert stat.S_IMODE(os.stat(support).st_mode) == 0o700
    before = target.read_bytes()
    with pytest.raises(MonitorJobError):
        write_plist(make(support_dir=str(support)), target, support)
    assert target.read_bytes() == before


def test_cli_dry_run_writes_nothing_and_write_creates_the_file(tmp_path):
    import yaml
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(INSTALL))
    plist, support, lines = tmp_path / "agent.plist", tmp_path / "s", []
    base = ["--config", str(config), "--plist", str(plist), "--support-dir", str(support)]
    assert cli.main(base, out=lines.append) == 0 and not plist.exists() and not support.exists()
    assert cli.main(base + ["--write"], out=lines.append) == 0 and plist.exists()
    assert any("has not been loaded" in l and "not armed" in l for l in lines)
    assert cli.main(base + ["--write"], out=lines.append) == 1            # second write refuses


def test_cli_refuses_the_candidate_file(tmp_path):
    import yaml
    candidate = tmp_path / "config.guardian-candidate.yaml"
    candidate.write_text(yaml.safe_dump(INSTALL))
    lines = []
    assert cli.main(["--config", str(candidate), "--plist", str(tmp_path / "a.plist"), "--write"],
                    out=lines.append) == 1
    assert not (tmp_path / "a.plist").exists()


def test_the_installer_cannot_load_arm_or_switch_anything():
    for name in ("guardian_v1_install_monitor.py", "modules/guardian_v1_monitor_job.py"):
        source = (Path(__file__).resolve().parent.parent / name).read_text()
        code = source.split('"""', 2)[2]                                   # skip the docstring
        assert not re.search(r"subprocess|os\.system|os\.exec|import socket|from socket|\.connect\(|power_off|"
                             r"enable_hardware_execution\(|\.arm\(", code), name
