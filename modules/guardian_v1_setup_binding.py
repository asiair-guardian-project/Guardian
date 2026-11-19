"""Fail-closed, read-only comparison of installation YAML to monitor launch settings.

This does not activate configuration, grant commissioning, or control hardware.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
from modules.guardian_v1_setup_config import SetupValidationError


@dataclass(frozen=True)
class MonitorBinding:
    asiair_host: str
    alpaca_host: str
    alpaca_port: int
    alpaca_device: int
    cycle_seconds: float


def compare_monitor_binding(config: Mapping[str, Any], active: MonitorBinding) -> dict[str, Any]:
    """Compare exact operational settings, returning no endpoint values.

    A match is necessary for safe adoption, not sufficient for commissioning.
    """
    if not isinstance(config, Mapping):
        raise SetupValidationError('Installation configuration must be a mapping')
    fields = (
        ('asiair', 'ip_address', active.asiair_host),
        ('roof', 'alpaca_host', active.alpaca_host),
        ('roof', 'alpaca_port', active.alpaca_port),
        ('roof', 'alpaca_device_number', active.alpaca_device),
        ('monitor', 'interval_seconds', active.cycle_seconds),
    )
    mismatches = []
    for section, key, expected in fields:
        section_values = config.get(section)
        if not isinstance(section_values, Mapping) or key not in section_values:
            mismatches.append(f'{section}.{key}: missing')
            continue
        actual = section_values[key]
        if type(actual) is bool or type(expected) is bool or actual != expected or (
            isinstance(expected, (int, float)) and not isinstance(actual, (int, float))
        ):
            mismatches.append(f'{section}.{key}: differs from active launch')
    source = config.get('roof', {}).get('source') if isinstance(config.get('roof'), Mapping) else None
    if source != 'alpaca':
        mismatches.append('roof.source: active monitor requires alpaca')
    return {'matches_active_monitor': not mismatches,
            'differences': mismatches,
            'safe_to_auto_apply': False,
            'commissioning_authorized': False}
