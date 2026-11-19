"""Offline composition of Phase B authority, bridge, and actual Starfront wiring.
No network: fake transport is injected into the real Kasa adapter.
"""
import pytest
from modules.guardian_types import SafetyPowerRole, SafetyPowerState
from modules.guardian_v1_commissioning_test_authority import (
    CommissioningTestScope, SingleUseTestAuthorization, TestAuthorizationError,
)
from modules.guardian_v1_phase_b_bridge import run_isolated_shutdown
from modules.guardian_v1_starfront_kasa import CONTROLLER_ID, compose_starfront_kasa

ROLES = frozenset({SafetyPowerRole.ASIAIR, SafetyPowerRole.MOUNT, SafetyPowerRole.ACCESSORIES})
EXPECTED = {(2, 'ASIAIR'), (3, 'Wave 150i'), (4, 'Pegasus')}

class FakeTransport:
    def __init__(self, fail_number=None):
        self.commands = []
        self.fail_number = fail_number
        self.off = set()
    def check_outlet(self, number, alias):
        return (number, alias) in EXPECTED
    def get_outlet_state(self, number, alias):
        return SafetyPowerState.OFF if number in self.off else SafetyPowerState.ON
    def power_off_outlet(self, number, alias):
        self.commands.append((number, alias))
        if number == self.fail_number:
            return False
        self.off.add(number)
        return True

def make_authorization():
    return SingleUseTestAuthorization(CommissioningTestScope(
        configuration_fingerprint='offline-test-fingerprint',
        controller_id=CONTROLLER_ID,
        roles=frozenset(role.name for role in ROLES),
    ))

def invoke(token, wiring, roles=ROLES):
    return run_isolated_shutdown(
        authorization=token,
        fingerprint='offline-test-fingerprint',
        controller_id=CONTROLLER_ID,
        roles=roles,
        execute_safety_power=wiring.execute_safety_power,
    )

def test_composed_success_and_single_use():
    fake = FakeTransport()
    wiring = compose_starfront_kasa(host='example.invalid', transport=fake)
    assert not fake.commands
    token = make_authorization()
    result = invoke(token, wiring)
    assert result.passed
    assert set(fake.commands) == EXPECTED
    assert all(number != 1 for number, _ in fake.commands)
    with pytest.raises(TestAuthorizationError):
        invoke(token, wiring)
    assert len(fake.commands) == 3

def test_composed_partial_failure_is_not_accepted():
    fake = FakeTransport(fail_number=3)
    wiring = compose_starfront_kasa(host='example.invalid', transport=fake)
    result = invoke(make_authorization(), wiring)
    assert not result.passed
    assert ('MOUNT', 'FAILED') in result.results
    assert set(fake.commands) == EXPECTED

def test_composed_protected_role_rejected_before_transport():
    fake = FakeTransport()
    wiring = compose_starfront_kasa(host='example.invalid', transport=fake)
    with pytest.raises(TestAuthorizationError):
        invoke(make_authorization(), wiring, {SafetyPowerRole.GUARDIAN_HOST})
    assert not fake.commands
