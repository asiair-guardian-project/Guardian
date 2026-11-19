"""Build the Guardian 1.0 monitor launchd job (WATCHING ONLY) from an installation config.

For a new operator: the setup wizard writes a candidate config; this module turns the (activated) installation config
into the launchd file that runs `guardian_v1_armed.py` as `org.guardian.v1.monitor`. The file it builds can NOT cut
power: it never contains --enable-hardware-execution (only guardian_stage_b.py adds that, on the operator's explicit
go-ahead). Nothing here loads the job, arms Guardian, contacts any device or switches power.
"""
from __future__ import annotations

import os
import plistlib
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from modules.guardian_v1_power_mapping import PowerMappingError, power_mapping_from_installation
from modules.guardian_v1_setup_config import SetupValidationError, validate_changes

LABEL = "org.guardian.v1.monitor"
HARDWARE_FLAG = "--enable-hardware-execution"
ALERT_LEVELS = ("off", "failure", "all")


class MonitorJobError(ValueError):
    pass


def default_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "GuardianV1"


def default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def check_installation(installation: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the five values the monitor is launched with, and the optional power section."""
    try:
        asiair = installation["asiair"]["ip_address"]
        roof = installation["roof"]
        strip = installation["kasa"]["power_strip_ip"]
        values = {"asiair": {"ip_address": asiair},
                  "roof": {"alpaca_host": roof["alpaca_host"], "alpaca_port": roof["alpaca_port"],
                           "alpaca_device_number": roof["alpaca_device_number"]},
                  "kasa": {"power_strip_ip": strip}}
    except (KeyError, TypeError) as error:
        raise MonitorJobError(f"The installation config is missing {error}") from None
    try:
        validate_changes(deepcopy(dict(installation)), values)
        power_mapping_from_installation(installation)
    except (SetupValidationError, PowerMappingError) as error:
        raise MonitorJobError(str(error)) from None
    return {"asiair_host": asiair, "alpaca_host": roof["alpaca_host"], "alpaca_port": roof["alpaca_port"],
            "alpaca_device": roof["alpaca_device_number"], "kasa_host": strip}


def build_plist(installation: Mapping[str, Any], *, project_dir, python, config_path,
                support_dir=None, alert_level="off") -> dict[str, Any]:
    if alert_level not in ALERT_LEVELS:
        raise MonitorJobError("alert level must be off, failure or all")
    for name, value in (("project folder", project_dir), ("python", python), ("installation config", config_path)):
        if not str(value).startswith("/"):
            raise MonitorJobError(f"{name} must be an absolute path")
    if "candidate" in Path(config_path).name:
        raise MonitorJobError(
            "That is the wizard's candidate file. Put it in place as the installation config first (a brand-new "
            "install only: copy it to config/config.yaml; if a config.yaml already exists do not overwrite it).")
    values = check_installation(installation)
    support = Path(support_dir) if support_dir else default_support_dir()
    arguments = [
        str(python), str(Path(project_dir) / "guardian_v1_armed.py"),
        "--recovery-file", str(support / "recovery.json"),
        "--operator-socket", str(support / "operator.sock"),
        "--asiair-host", values["asiair_host"],
        "--alpaca-host", values["alpaca_host"],
        "--alpaca-port", str(values["alpaca_port"]),
        "--alpaca-device", str(values["alpaca_device"]),
        "--kasa-host", values["kasa_host"],
        "--cycle-seconds", "5",
        "--installation-config", str(config_path),
        "--commissioning-record", str(support / "commissioning.json"),
        "--ups-low-battery-percent", "35",
        "--ups-unreadable-grace-seconds", "900",
        "--alert-level", alert_level,
    ]
    if HARDWARE_FLAG in arguments:                       # cannot happen; belt and braces
        raise MonitorJobError("refusing to build a job that can cut power")
    return {
        "Label": LABEL,
        "ProgramArguments": arguments,
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "WorkingDirectory": str(project_dir),
        "StandardOutPath": str(support / "monitor_stdout.log"),
        "StandardErrorPath": str(support / "monitor_stderr.log"),
    }


def write_plist(plist: Mapping[str, Any], path, support_dir=None) -> Path:
    """Write a NEW launchd file (never overwrites) and create the private support folder."""
    target = Path(path)
    support = Path(support_dir) if support_dir else default_support_dir()
    support.mkdir(parents=True, exist_ok=True)
    os.chmod(support, 0o700)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except FileExistsError:
        raise MonitorJobError(f"{target} already exists; this command never overwrites a launchd file") from None
    try:
        with os.fdopen(fd, "wb") as handle:
            plistlib.dump(dict(plist), handle)
    except BaseException:
        try:
            target.unlink()
        finally:
            raise
    return target


def next_steps(plist_path) -> list[str]:
    return [
        f"The watching-only monitor job was written to {plist_path}. It has not been loaded and Guardian is not armed.",
        "Before loading it, make sure no other Guardian monitor (for example v0.6) is running on this Mac.",
        f"To start it (watching only): launchctl bootstrap gui/$(id -u) \"{plist_path}\"",
        "Then check it with: .venv/bin/python guardian_stage_b.py status   (expect: watching only, disarmed).",
        "This monitor cannot cut power. Letting v1.0 cut power is a separate, deliberate step (guardian_stage_b.py), "
        "to be done only after commissioning and a supervised first night.",
    ]
