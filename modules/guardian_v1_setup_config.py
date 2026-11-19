"""Read-only configuration inspection and proposed-change validation for Phase C.

No write path or hardware access is intentionally provided by this module.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import ipaddress
import yaml


class SetupValidationError(ValueError):
    pass


# Only fields with established meanings in the current installation YAML.
EDITABLE = {
    "asiair": {"ip_address", "timeout_seconds"},
    "roof": {"source", "stale_after_seconds", "alpaca_host", "alpaca_port",
             "alpaca_device_number", "alpaca_timeout_seconds"},
    "kasa": {"power_strip_ip"},
    "monitor": {"interval_seconds"},
}


def read_installation(path: str | Path) -> dict[str, Any]:
    """Read installation YAML without modifying it."""
    with Path(path).open("r", encoding="utf-8") as stream:
        result = yaml.safe_load(stream)
    if not isinstance(result, dict):
        raise SetupValidationError("Configuration must be a YAML mapping")
    return result


def _endpoint(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SetupValidationError(f"{field}: nonempty host/IP required")
    if any(ch.isspace() for ch in value) or any(ch in value for ch in '/\\:@'):
        raise SetupValidationError(f"{field}: invalid host/IP")
    if len(value) > 253:
        raise SetupValidationError(f"{field}: host too long")
    try:
        ipaddress.ip_address(value)
        return
    except ValueError:
        pass
    labels = value.split('.')
    if any(not label or len(label) > 63 or label[0] == '-' or label[-1] == '-' or
           not all(ch.isascii() and (ch.isalnum() or ch == '-') for ch in label)
           for label in labels):
        raise SetupValidationError(f"{field}: invalid hostname")


def _positive_number(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0 < value <= 3600):
        raise SetupValidationError(f"{field}: expected positive number <= 3600")


def validate_changes(current: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """Return validated proposed config; never write or activate it.

    Intentionally disallows changing mount and power outlet mappings until
    runtime commissioning identity and authorization are fully integrated.
    """
    if not isinstance(changes, Mapping) or not changes:
        raise SetupValidationError("No changes supplied")
    candidate = deepcopy(dict(current))
    for section, fields in changes.items():
        if section not in EDITABLE or not isinstance(fields, Mapping) or not fields:
            raise SetupValidationError(f"Section {section!r} cannot be edited in this phase")
        if not isinstance(candidate.get(section), dict):
            raise SetupValidationError(f"Missing existing section: {section}")
        for field, value in fields.items():
            if field not in EDITABLE[section] or field not in candidate[section]:
                raise SetupValidationError(f"Unsupported field: {section}.{field}")
            name = f"{section}.{field}"
            if field in ("ip_address", "power_strip_ip", "alpaca_host"):
                _endpoint(value, name)
            elif field in ("alpaca_port", "alpaca_device_number"):
                if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= (65535 if field == 'alpaca_port' else 255)) or (field == 'alpaca_port' and value == 0):
                    raise SetupValidationError(f"{name}: invalid port/device number")
            elif field == "source":
                if value != candidate[section][field]:
                    raise SetupValidationError("Changing roof source requires separate provider validation")
            else:
                _positive_number(value, name)
            candidate[section][field] = value
    return candidate


def redacted_overview(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Expose field presence only, never endpoints or credentials."""
    return {section: sorted(fields.keys()) for section, fields in configuration.items()
            if section in EDITABLE and isinstance(fields, Mapping)}
