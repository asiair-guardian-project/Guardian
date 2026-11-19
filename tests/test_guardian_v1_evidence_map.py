from guardian_v1_evidence_map import report
from modules.commissioning import CommissioningCheck
import pytest


def test_all_eight_checks_remain_unauthorized():
    result = report('a' * 64)
    assert set(result['checks']) == {check.name for check in CommissioningCheck}
    assert result['verified_count'] == 0
    assert result['pending_count'] == 8
    assert result['hardware_authorized'] is False
    assert all(item['commissioning_result'] == 'NOT_TESTED' for item in result['checks'].values())


def test_invalid_fingerprint_rejected():
    with pytest.raises(ValueError):
        report('bad')
