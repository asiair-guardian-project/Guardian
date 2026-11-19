"""Phase B isolated bridge tests. All callbacks are in-memory fakes."""
from types import SimpleNamespace
import pytest

from modules.guardian_types import SafetyPowerRole as R, SafetyPowerResult as S
from modules.guardian_v1_commissioning_test_authority import (
    CommissioningTestScope, SingleUseTestAuthorization, TestAuthorizationError,
)
from modules.guardian_v1_phase_b_bridge import run_isolated_shutdown

ROLES = {R.ASIAIR, R.MOUNT, R.ACCESSORIES}


def token():
    return SingleUseTestAuthorization(CommissioningTestScope(
        configuration_fingerprint='fingerprint', controller_id='controller',
        roles=frozenset(r.name for r in ROLES),
    ))


def invoke(t, cb, **kw):
    return run_isolated_shutdown(
        authorization=t, fingerprint=kw.get('fingerprint', 'fingerprint'),
        controller_id='controller', roles=kw.get('roles', ROLES),
        execute_safety_power=cb,
    )


def test_generic_callback_all_roles_verified():
    calls = []
    def cb(roles):
        calls.append(roles)
        return [SimpleNamespace(role=r, result=S.VERIFIED_OFF) for r in roles]
    result = invoke(token(), cb)
    assert result.passed and len(result.results) == 3
    assert calls == [ROLES]


def test_failed_verification_is_not_pass():
    def cb(roles):
        return [SimpleNamespace(role=r, result=S.FAILED if r is R.MOUNT else S.VERIFIED_OFF) for r in roles]
    assert not invoke(token(), cb).passed


def test_missing_role_is_not_pass():
    assert not invoke(token(), lambda roles: [SimpleNamespace(role=R.ASIAIR, result=S.VERIFIED_OFF)]).passed


def test_replay_is_rejected_without_second_call():
    calls = []
    def cb(roles):
        calls.append(1)
        return [SimpleNamespace(role=r, result=S.VERIFIED_OFF) for r in roles]
    t = token()
    invoke(t, cb)
    with pytest.raises(TestAuthorizationError):
        invoke(t, cb)
    assert len(calls) == 1


def test_fingerprint_mismatch_burns_authorization():
    calls = []
    t = token()
    with pytest.raises(TestAuthorizationError):
        invoke(t, lambda roles: calls.append(1), fingerprint='wrong')
    with pytest.raises(TestAuthorizationError):
        invoke(t, lambda roles: calls.append(1))
    assert not calls


def test_protected_role_refused_without_callback():
    calls = []
    with pytest.raises(TestAuthorizationError):
        invoke(token(), lambda roles: calls.append(1), roles={R.GUARDIAN_HOST})
    assert not calls


def test_executor_exception_propagates_and_token_consumed():
    t = token()
    def cb(roles):
        raise ConnectionError('simulated offline controller')
    with pytest.raises(ConnectionError):
        invoke(t, cb)
    with pytest.raises(TestAuthorizationError):
        invoke(t, cb)


def test_duplicate_result_rejected():
    with pytest.raises(RuntimeError, match='duplicate'):
        invoke(token(), lambda roles: [SimpleNamespace(role=R.ASIAIR, result=S.VERIFIED_OFF)] * 2)
