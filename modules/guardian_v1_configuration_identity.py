"""Fail-closed, offline configuration identity gate for Phase C.

This module does not authorize activation, commissioning, or hardware actions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from modules.guardian_v1_setup_config import read_installation
from modules.guardian_v1_setup_binding import MonitorBinding, compare_monitor_binding


class ConfigurationIdentityError(ValueError):
    pass


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            raise ConfigurationIdentityError('Non-string configuration key')
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not __import__('math').isfinite(value):
            raise ConfigurationIdentityError('Non-finite configuration number')
        return value
    raise ConfigurationIdentityError('Unsupported configuration value type')


def semantic_fingerprint(configuration: Mapping[str, Any]) -> str:
    """Hash all installation settings, including settings not yet modeled as safety roles."""
    encoded = json.dumps(_canonical(configuration), sort_keys=True,
                         separators=(',', ':'), ensure_ascii=True,
                         allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def inspect_configuration_identity(active_path: str | Path,
                                   candidate_path: str | Path,
                                   binding: MonitorBinding) -> dict[str, Any]:
    """Inspect current files and monitor binding; NEVER grant authorization."""
    active = Path(active_path).expanduser().resolve(strict=True)
    candidate = Path(candidate_path).expanduser().resolve(strict=True)
    if active == candidate or active.parent != candidate.parent:
        raise ConfigurationIdentityError('Candidate must be separate and beside active YAML')
    current = read_installation(active)
    proposed = read_installation(candidate)
    if set(current) != set(proposed):
        raise ConfigurationIdentityError('Configuration sections differ')
    changed = []
    for section in sorted(current):
        before, after = current[section], proposed[section]
        if not isinstance(before, dict) or not isinstance(after, dict) or set(before) != set(after):
            raise ConfigurationIdentityError('Configuration field structure differs')
        changed.extend(f'{section}.{key}' for key in sorted(before) if before[key] != after[key])
    active_binding = compare_monitor_binding(current, binding)
    candidate_binding = compare_monitor_binding(proposed, binding)
    return {
        'active_identity': semantic_fingerprint(current),
        'candidate_identity': semantic_fingerprint(proposed),
        'active_file_sha256': hashlib.sha256(active.read_bytes()).hexdigest(),
        'candidate_file_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'changed_fields': changed,
        'active_matches_monitor_checked_fields': active_binding['matches_active_monitor'],
        'candidate_matches_monitor_checked_fields': candidate_binding['matches_active_monitor'],
        'commissioning_evidence_revalidation_required': bool(changed),
        'runtime_identity_enforced': False,
        'activation_authorized': False,
        'commissioning_authorized': False,
        'hardware_commands': 0,
        'reason': 'Runtime identity and commissioning evidence gates are not yet integrated',
    }
