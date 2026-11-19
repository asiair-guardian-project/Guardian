"""Single-use, in-memory authorization for an isolated commissioning rehearsal.

Not wired to GuardianV1Mode, production ARM, or hardware executors.
Never use this object alone as authorization for physical switching.
"""
from dataclasses import dataclass
from enum import Enum


class TestAuthorizationError(RuntimeError):
    pass


class TestAuthorizationState(Enum):
    NEW = 'NEW'
    CONSUMED = 'CONSUMED'
    REVOKED = 'REVOKED'


@dataclass(frozen=True)
class CommissioningTestScope:
    configuration_fingerprint: str
    controller_id: str
    roles: frozenset[str]
    purpose: str = 'PHASE_B_ISOLATED_REHEARSAL'

    def __post_init__(self):
        if not self.configuration_fingerprint or not self.controller_id:
            raise ValueError('fingerprint and controller are required')
        if not self.roles or not self.roles <= {'ASIAIR', 'MOUNT', 'ACCESSORIES'}:
            raise ValueError('roles must be a nonempty subset of safety shutdown roles')
        if self.purpose != 'PHASE_B_ISOLATED_REHEARSAL':
            raise ValueError('unsupported purpose')


class SingleUseTestAuthorization:
    """One-way token, scoped to a test identity. No filesystem/network I/O."""

    def __init__(self, scope: CommissioningTestScope):
        self.scope = scope
        self.state = TestAuthorizationState.NEW

    def consume(self, *, fingerprint: str, controller_id: str, roles: set[str]):
        if self.state is not TestAuthorizationState.NEW:
            raise TestAuthorizationError('authorization is not available')
        # A mismatch burns the token: a failed request cannot be retried with new args.
        self.state = TestAuthorizationState.CONSUMED
        if (fingerprint != self.scope.configuration_fingerprint or
                controller_id != self.scope.controller_id or
                frozenset(roles) != self.scope.roles):
            raise TestAuthorizationError('scope mismatch')
        return True

    def revoke(self):
        self.state = TestAuthorizationState.REVOKED
