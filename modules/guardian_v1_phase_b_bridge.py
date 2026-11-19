"""Isolated Phase B bridge for the existing safety-power callback.

No production ARM/mode mutation, no controller construction, no live CLI.
Caller must provide a separately vetted execution callback; tests use fakes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from modules.guardian_types import SafetyPowerRole, SafetyPowerResult
from modules.guardian_v1_commissioning_test_authority import TestAuthorizationError

ALLOWED = frozenset({SafetyPowerRole.ASIAIR, SafetyPowerRole.MOUNT, SafetyPowerRole.ACCESSORIES})


@dataclass(frozen=True)
class BridgeResult:
    timestamp_utc: str
    controller_id: str
    roles: tuple[str, ...]
    results: tuple[tuple[str, str], ...]
    passed: bool


def run_isolated_shutdown(*, authorization, fingerprint, controller_id, roles, execute_safety_power):
    """Consume once, then call the already-configured generic executor.

    This bridge alone is NOT permission for physical operation. The caller
    must independently establish exclusive ownership, physical preflight,
    operator approval, and persistent evidence before supplying a real executor.
    """
    roles = frozenset(roles)
    if not roles or not roles <= ALLOWED:
        raise TestAuthorizationError('invalid or protected role in request')
    authorization.consume(
        fingerprint=fingerprint, controller_id=controller_id,
        roles={r.name for r in roles},
    )
    records = execute_safety_power(set(roles))
    if not isinstance(records, (list, tuple)):
        raise RuntimeError('executor did not return role records')
    by_role = {}
    for record in records:
        if record.role in by_role or record.role not in roles:
            raise RuntimeError('duplicate or unexpected role result')
        by_role[record.role] = record.result
    outcome = tuple(sorted((role.name, by_role.get(role, SafetyPowerResult.FAILED).name) for role in roles))
    return BridgeResult(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        controller_id=controller_id,
        roles=tuple(sorted(role.name for role in roles)),
        results=outcome,
        passed=all(result == 'VERIFIED_OFF' for _, result in outcome),
    )
