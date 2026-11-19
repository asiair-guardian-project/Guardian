"""Logic for the Guardian 1.0 first-run setup wizard (step one).

What it does: collects the four installation settings (ASIAIR, roof status source, power strip address,
monitor interval), runs READ-ONLY checks against the real equipment, and writes ONE new candidate
file. What it never does: switch power, ARM or DISARM, contact the monitor, activate or replace any
configuration, or approve commissioning. Every check catches its own errors and reports them;
nothing here raises into the caller for an equipment problem.

The outlet screen writes the `power` section (see guardian_v1_power_mapping): which outlet powers the computer running
Guardian (never switched) and which outlets Guardian cuts for the ASIAIR, the mount and the accessories.
"""
from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from modules.guardian_v1_power_mapping import PowerMappingError, parse_power_section
from modules.guardian_v1_setup_config import SetupValidationError, validate_changes

CANDIDATE_NAME = "config.guardian-candidate.yaml"

# Starfront's public Alpaca endpoint is the same for every Starfront operator; the device number is theirs.
DEFAULT_ALPACA_HOST = "alpaca-api.tx.starfront.space"
DEFAULT_ALPACA_PORT = 443

# A complete installation with neutral placeholders; every operator-facing field is overwritten by the form.
_BASE = {
    "asiair": {"ip_address": "192.0.2.10", "timeout_seconds": 2},
    "kasa": {"power_strip_ip": "192.0.2.20"},
    "roof": {"source": "alpaca", "alpaca_host": DEFAULT_ALPACA_HOST, "alpaca_port": DEFAULT_ALPACA_PORT,
             "alpaca_device_number": 0, "alpaca_timeout_seconds": 5, "stale_after_seconds": None},
    "monitor": {"interval_seconds": 5},
}

FIELDS = {   # form field -> (section, name, kind)
    "asiair_ip": ("asiair", "ip_address", "text"),
    "roof_host": ("roof", "alpaca_host", "text"),
    "roof_port": ("roof", "alpaca_port", "int"),
    "roof_device": ("roof", "alpaca_device_number", "int"),
    "strip_ip": ("kasa", "power_strip_ip", "text"),
}
POWER_FIELDS = {   # form field -> (entry in the power section, number or alias)
    "host_outlet_number": ("host_outlet", "number"), "host_outlet_alias": ("host_outlet", "alias"),
    "asiair_outlet_number": ("asiair", "number"), "asiair_outlet_alias": ("asiair", "alias"),
    "mount_outlet_number": ("mount", "number"), "mount_outlet_alias": ("mount", "alias"),
    "accessories_outlet_number": ("accessories", "number"), "accessories_outlet_alias": ("accessories", "alias"),
}
REQUIRED = tuple(FIELDS) + tuple(POWER_FIELDS)


class WizardError(ValueError):
    pass


def defaults() -> dict[str, Any]:
    return {"roof_host": DEFAULT_ALPACA_HOST, "roof_port": DEFAULT_ALPACA_PORT}


def _coerce(name: str, value: Any, kind: str):
    if kind == "int":
        if isinstance(value, bool):
            raise WizardError(f"{name}: a whole number is required")
        if isinstance(value, str):
            value = value.strip()
        try:
            return int(value)
        except (TypeError, ValueError):
            raise WizardError(f"{name}: a whole number is required") from None
    if not isinstance(value, str):
        raise WizardError(f"{name}: text is required")
    return value.strip()


def build_installation(form: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the form with the same rules the Setup screen uses and return a complete installation mapping."""
    if not isinstance(form, Mapping):
        raise WizardError("The form must be a set of named fields")
    unknown = set(form) - set(FIELDS) - set(POWER_FIELDS) - {"controller"}
    if unknown:
        raise WizardError("Unknown field: " + ", ".join(sorted(map(str, unknown))))
    missing = [name for name in REQUIRED if name not in form or form[name] in (None, "")]
    if missing:
        raise WizardError("Missing: " + ", ".join(missing))
    changes: dict[str, dict[str, Any]] = {}
    for name, (section, key, kind) in FIELDS.items():
        changes.setdefault(section, {})[key] = _coerce(name, form[name], kind)
    try:
        installation = validate_changes(deepcopy(_BASE), changes)
    except SetupValidationError as error:
        raise WizardError(str(error)) from None
    installation["power"] = _power_section(form)
    return installation


def _power_section(form: Mapping[str, Any]) -> dict[str, Any]:
    """Build and validate the `power` section with the same rules the engine applies at startup."""
    entries: dict[str, dict[str, Any]] = {}
    for name, (entry, part) in POWER_FIELDS.items():
        value = form[name]
        if part == "number":
            value = _coerce(name, value, "int")
        elif not isinstance(value, str):
            raise WizardError(f"{name}: text is required")
        else:
            value = value.strip()
        entries.setdefault(entry, {})[part] = value
    controller = form.get("controller") or "kasa_hs300"
    if controller not in ("kasa_hs300", "digital_loggers_rest"):
        raise WizardError("controller: choose Kasa HS300 or Digital Loggers")
    section = {"type": controller, "host_outlet": entries.pop("host_outlet"), "targets": entries}
    try:
        parse_power_section(section)
    except PowerMappingError as error:
        raise WizardError(str(error)) from None
    return section


# ---- read-only checks ------------------------------------------------------------------------

def _result(ok: bool, detail: str) -> dict[str, Any]:
    return {"ok": bool(ok), "detail": detail}


def check_asiair(host: str, *, ping: Callable[..., bool] | None = None) -> dict[str, Any]:
    """Is the ASIAIR answering a ping at this address? Read-only."""
    try:
        build_installation({**_probe_defaults(), "asiair_ip": host})
    except WizardError as error:
        return _result(False, str(error))
    try:
        if ping is None:
            from modules.asiair_monitor import asiair_available as ping
        reachable = ping(host.strip())
    except Exception as error:   # a missing ping tool or a network error is a report, never a crash
        return _result(False, f"The check could not run: {error}")
    return _result(reachable, "The ASIAIR answered" if reachable else "No answer from that address")


def check_roof(host: str, port: Any, device: Any, *, reader: Callable[..., dict] | None = None) -> dict[str, Any]:
    """Read the observatory safety monitor once. Read-only; says what it read, never what to do."""
    try:
        values = build_installation({**_probe_defaults(), "roof_host": host, "roof_port": port,
                                     "roof_device": device})["roof"]
    except WizardError as error:
        return _result(False, str(error))
    try:
        if reader is None:
            from modules.alpaca_safety_monitor import read_alpaca_safety_status as reader
        reading = reader(values["alpaca_host"], values["alpaca_port"], values["alpaca_device_number"],
                         timeout_seconds=values["alpaca_timeout_seconds"])
    except Exception as error:
        return _result(False, f"Could not read the safety monitor: {error}")
    safe = reading.get("is_safe") if isinstance(reading, Mapping) else None
    if not isinstance(safe, bool):
        return _result(False, "The safety monitor replied, but not with a clear safe or not-safe answer")
    return _result(True, "Read OK: the roof reports " + ("SAFE (open)" if safe else "NOT SAFE (closed)"))


def check_strip(host: str, *, ping: Callable[..., bool] | None = None) -> dict[str, Any]:
    """Is the strip answering a ping? Read-only, and the lightest touch there is: a ping opens no session with the
    strip and sends it no command. (Whether it is really an HS300, and its outlet names, is for a later step that
    signs in to the strip; this one only says the address answers.)"""
    try:
        build_installation({**_probe_defaults(), "strip_ip": host})
    except WizardError as error:
        return _result(False, str(error))
    try:
        if ping is None:
            from modules.asiair_monitor import asiair_available as ping   # a plain ping; the name is historical
        reachable = ping(host.strip())
    except Exception as error:
        return _result(False, f"The check could not run: {error}")
    return _result(reachable, "The strip answered a ping" if reachable else "No answer from that address")


def _probe_defaults() -> dict[str, Any]:
    """Valid stand-ins so one field can be validated on its own."""
    return {"asiair_ip": "192.0.2.10", "roof_host": DEFAULT_ALPACA_HOST, "roof_port": DEFAULT_ALPACA_PORT,
            "roof_device": 0, "strip_ip": "192.0.2.20",
            "host_outlet_number": 1, "host_outlet_alias": "Host computer",
            "asiair_outlet_number": 2, "asiair_outlet_alias": "ASIAIR",
            "mount_outlet_number": 3, "mount_outlet_alias": "Mount",
            "accessories_outlet_number": 4, "accessories_outlet_alias": "Accessories"}


# ---- the only write -------------------------------------------------------------------------

def write_candidate(folder: str | Path, installation: Mapping[str, Any]) -> dict[str, Any]:
    """Create config.guardian-candidate.yaml in `folder`. Never overwrites, never activates."""
    destination = Path(folder).expanduser().absolute() / CANDIDATE_NAME
    if not destination.parent.is_dir():
        raise WizardError("The folder does not exist")
    if destination.exists() or destination.is_symlink():
        raise WizardError(f"{CANDIDATE_NAME} already exists; refusing to overwrite it")
    encoded = yaml.safe_dump(dict(installation), sort_keys=False, allow_unicode=True).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, 0o600)       # private: it holds the operator's addresses
    try:
        with os.fdopen(descriptor, "wb") as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {"written": True, "path": str(destination), "activated": False, "commissioning_authorized": False}


def next_steps(path: str, installation: Mapping[str, Any] | None = None) -> list[str]:
    dli = (installation or {}).get("power", {}).get("type") == "digital_loggers_rest"
    steps = [
        f"Review {path} by eye. Nothing has been activated and no power was switched.",
        "If you already have a configuration file (for example one shared with Guardian 0.6), do NOT copy this file over "
        "it: this file holds only the four Guardian 1.0 settings, and replacing a larger file would delete the others.",
        "Activating a configuration, and commissioning it (the equipment checks you verify yourself), "
        "are separate deliberate steps that this page does not do.",
        "Guardian reads your Kasa account sign-in from its own secure storage (the macOS Keychain on a Mac). "
        "This page never asks for it and never stores it. Save it with:  guardian_v1_credentials.py set kasa  "
        "(you type the password into macOS's own hidden prompt).",
        "Check each outlet name against the Kasa app exactly. Before every power-off Guardian requires the strip's own "
        "name for that outlet to match, and it refuses to switch the outlet you named as the computer's. "
        "guardian_v1_check_outlets.py --config <your installation config> compares your names with the strip "
        "(read-only).",
        "This file includes your outlet mapping. Guardian treats any change to it as a new configuration: the "
        "commissioning checks must be done again for it.",
        "Commissioning tools follow this outlet mapping: guardian_v1_outlet_test.py list / test --outlet N tries "
        "Guardian's power-off on ONE spare outlet, and guardian_v1_rehearsal.py --dry-run shows the exact outlets a "
        "rehearsal would cut (and the confirmation word it needs). Do both only when the equipment is safe to switch.",
        "To run Guardian 1.0 as a watching-only monitor, put this configuration in place as config/config.yaml (a "
        "brand-new install only) and run:  guardian_v1_install_monitor.py --config config/config.yaml  (it shows the "
        "monitor job first; add --write to create it). It can not cut power.",
    ]
    if dli:
        steps[3:5] = [
            "Digital Loggers support has NOT been tested on real hardware. Before relying on it, run "
            "guardian_v1_dli_probe.py (it only reads) and confirm every outlet name it prints matches what you entered.",
            "Guardian reads the controller's user name and password from DLI_USERNAME / DLI_PASSWORD, or from the macOS "
            "Keychain (items 'Guardian Digital Loggers Username' and 'Guardian Digital Loggers Password', account "
            "'guardian'). This page never asks for them and never stores them. Outlet numbers are the ones printed on "
            "the unit (1-8); names are the controller's own outlet names, typed exactly. Before every power-off "
            "Guardian requires the controller's name for that outlet to match, and it refuses to switch the outlet "
            "you named as the computer's. Save the sign-in with:  guardian_v1_credentials.py set dli  and compare names "
            "with:  guardian_v1_check_outlets.py --config <your installation config>  (read-only).",
        ]
    return steps
