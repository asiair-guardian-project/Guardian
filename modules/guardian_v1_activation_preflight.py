"""Read-only candidate activation preflight. NEVER authorizes activation or ARM."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
from modules.guardian_v1_setup_config import read_installation
from modules.guardian_v1_setup_binding import MonitorBinding, compare_monitor_binding


def activation_preflight(active_path: str | Path, candidate_path: str | Path,
                         binding: MonitorBinding) -> dict[str, Any]:
    """Compare files and launch binding without exposing configuration values."""
    active = Path(active_path).expanduser().resolve(strict=True)
    candidate = Path(candidate_path).expanduser().resolve(strict=True)
    if active == candidate or candidate.parent != active.parent:
        raise ValueError('Candidate must be separate and beside active configuration')
    original = read_installation(active)
    proposed = read_installation(candidate)
    if set(original) != set(proposed):
        raise ValueError('Candidate section structure differs from active configuration')
    differences = []
    for section in sorted(original):
        old, new = original[section], proposed[section]
        if isinstance(old, dict) and isinstance(new, dict):
            if set(old) != set(new):
                raise ValueError('Candidate field structure differs from active configuration')
            differences.extend(f'{section}.{field}' for field in sorted(old) if old[field] != new[field])
        elif old != new:
            differences.append(section)
    comparison = compare_monitor_binding(proposed, binding)
    return {
        'active_sha256': hashlib.sha256(active.read_bytes()).hexdigest(),
        'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'changed_fields': differences,
        'matches_active_monitor_checked_fields': comparison['matches_active_monitor'],
        'monitor_differences': comparison['differences'],
        'requires_commissioning_review': bool(differences),
        'configuration_identity_bound_to_runtime': False,
        'activation_authorized': False,
        'commissioning_authorized': False,
        'hardware_commands': 0,
        'reason': 'Activation disabled until runtime identity, rollback, and commissioning gates are integrated',
    }
