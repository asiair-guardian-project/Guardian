import pytest
from modules.guardian_v1_commissioning_test_authority import (
    CommissioningTestScope, SingleUseTestAuthorization,
    TestAuthorizationError as AuthorizationError, TestAuthorizationState as AuthorizationState,
)


def new():
    return SingleUseTestAuthorization(CommissioningTestScope(
        configuration_fingerprint='fp', controller_id='fake_controller',
        roles=frozenset({'ASIAIR', 'MOUNT', 'ACCESSORIES'})))


def test_one_success_only():
    auth = new()
    assert auth.consume(fingerprint='fp', controller_id='fake_controller', roles={'ASIAIR', 'MOUNT', 'ACCESSORIES'})
    with pytest.raises(AuthorizationError):
        auth.consume(fingerprint='fp', controller_id='fake_controller', roles={'ASIAIR', 'MOUNT', 'ACCESSORIES'})


@pytest.mark.parametrize('changes', [
    {'fingerprint': 'wrong'}, {'controller_id': 'other'},
    {'roles': {'ASIAIR'}}, {'roles': {'ASIAIR', 'MOUNT', 'ACCESSORIES', 'HOST'}}
])
def test_mismatch_burns_authorization(changes):
    auth = new()
    args = dict(fingerprint='fp', controller_id='fake_controller', roles={'ASIAIR', 'MOUNT', 'ACCESSORIES'})
    args.update(changes)
    with pytest.raises(AuthorizationError):
        auth.consume(**args)
    assert auth.state is AuthorizationState.CONSUMED
    with pytest.raises(AuthorizationError):
        auth.consume(fingerprint='fp', controller_id='fake_controller', roles={'ASIAIR', 'MOUNT', 'ACCESSORIES'})


def test_revocation_is_terminal():
    auth = new()
    auth.revoke()
    with pytest.raises(AuthorizationError):
        auth.consume(fingerprint='fp', controller_id='fake_controller', roles={'ASIAIR', 'MOUNT', 'ACCESSORIES'})


@pytest.mark.parametrize('roles', [frozenset(), frozenset({'HOST'}), frozenset({'ASIAIR', 'HOST'})])
def test_protected_or_empty_roles_rejected(roles):
    with pytest.raises(ValueError):
        CommissioningTestScope('fp', 'fake_controller', roles)


def test_missing_scope_identity_rejected():
    with pytest.raises(ValueError):
        CommissioningTestScope('', 'fake_controller', frozenset({'ASIAIR'}))
