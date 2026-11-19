import json
import pytest
from modules.guardian_v1_commissioning_test_authority import CommissioningTestScope, TestAuthorizationError as AuthorizationError
from modules.guardian_v1_phase_b_durable_authority import DurableTestAuthorization


def authority(tmp_path, test_id='test-one'):
    scope = CommissioningTestScope(configuration_fingerprint='fp', controller_id='hs300', roles=frozenset({'ASIAIR', 'MOUNT', 'ACCESSORIES'}))
    return DurableTestAuthorization(journal_dir=tmp_path, test_id=test_id, scope=scope)


def consume(a, **overrides):
    args = dict(fingerprint='fp', controller_id='hs300', roles={'ASIAIR', 'MOUNT', 'ACCESSORIES'})
    args.update(overrides)
    return a.consume(**args)


def test_consumption_is_durable(tmp_path):
    a = authority(tmp_path)
    assert consume(a)
    record = json.loads(a.marker.read_text())
    assert record['event'] == 'PHASE_B_AUTHORIZATION_CONSUMED'
    assert record['commissioning_status'] == 'NOT_AUTHORIZED'


def test_cannot_reuse_after_recreation(tmp_path):
    consume(authority(tmp_path))
    with pytest.raises(AuthorizationError, match='already consumed'):
        consume(authority(tmp_path))


def test_mismatch_consumes_and_cannot_retry(tmp_path):
    a = authority(tmp_path)
    with pytest.raises(AuthorizationError, match='scope mismatch'):
        consume(a, controller_id='other')
    with pytest.raises(AuthorizationError, match='already consumed'):
        consume(authority(tmp_path))


def test_outcome_requires_consumption(tmp_path):
    with pytest.raises(AuthorizationError):
        authority(tmp_path).record_outcome(status='PASS', details={})


def test_outcome_is_immutable(tmp_path):
    a = authority(tmp_path)
    consume(a)
    a.record_outcome(status='EXCEPTION', details={'error_type': 'TimeoutError'})
    with pytest.raises(AuthorizationError):
        a.record_outcome(status='PASS', details={})
    assert a.marker.exists()


def test_invalid_test_id_rejected(tmp_path):
    with pytest.raises(ValueError):
        authority(tmp_path, '../escape')


def test_invalid_outcome_rejected(tmp_path):
    a = authority(tmp_path)
    consume(a)
    with pytest.raises(ValueError):
        a.record_outcome(status='AUTHORIZED', details={})


def test_parallel_consumption_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    def attempt(_):
        try:
            consume(authority(tmp_path))
            return True
        except AuthorizationError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1
