import json
import pytest
from guardian_v1_commissioning_reconcile import reconcile

FP = 'fingerprint-123'

def fixture(tmp_path, *, status='PASS', fingerprint=FP, verified=True, role_result='VERIFIED_OFF', marker_fp=FP):
    folder = tmp_path / 'phase_b_live'
    folder.mkdir()
    test_id = 'phase_b_live_20261029_01'
    roles = ['ACCESSORIES', 'ASIAIR', 'MOUNT']
    details = {'test_id':test_id, 'configuration_fingerprint':fingerprint,
               'controller_id':'starfront-hs300', 'commissioning_status':'NOT_AUTHORIZED',
               'status':status, 'independent_outlet_verification':verified,
               'bridge': {'passed':status=='PASS', 'roles':roles,
                          'results':[[r,role_result] for r in roles]},
               'physical_roof_event':'NOT_TESTED'}
    outcome = {'event':'PHASE_B_TEST_OUTCOME','test_id':test_id,
               'status':status, 'details':details, 'commissioning_status':'NOT_AUTHORIZED'}
    scope = {'configuration_fingerprint':marker_fp,'controller_id':'starfront-hs300','roles':roles}
    marker = {'event':'PHASE_B_AUTHORIZATION_CONSUMED','test_id':test_id,
              'requested':scope, 'approved_scope':scope,
              'commissioning_status':'NOT_AUTHORIZED'}
    (folder / (test_id+'.outcome.json')).write_text(json.dumps(outcome))
    (folder / (test_id+'.consumed.json')).write_text(json.dumps(marker))
    return folder

def test_real_nested_schema_passes_without_authorization(tmp_path):
    fixture(tmp_path)
    result = reconcile(tmp_path, FP)
    assert result['physical_test_status']=='PASS'
    assert result['commissioning_status']=='NOT_AUTHORIZED'
    assert result['changes_production_audit'] is False
    assert result['physical_roof_event']=='NOT_TESTED'
    assert result['authorization_sha256']

@pytest.mark.parametrize('kwargs', [
    {'status':'FAIL'}, {'verified':False}, {'fingerprint':'wrong'},
    {'role_result':'FAILED'}, {'marker_fp':'wrong'},
])
def test_invalid_evidence_rejected(tmp_path, kwargs):
    fixture(tmp_path, **kwargs)
    with pytest.raises(ValueError): reconcile(tmp_path, FP)

def test_missing_consumption_rejected(tmp_path):
    folder=fixture(tmp_path)
    (folder/'phase_b_live_20261029_01.consumed.json').unlink()
    with pytest.raises(ValueError): reconcile(tmp_path, FP)

def test_mismatched_wrapper_status_rejected(tmp_path):
    folder=fixture(tmp_path)
    path=folder/'phase_b_live_20261029_01.outcome.json'
    obj=json.loads(path.read_text());obj['status']='UNKNOWN';path.write_text(json.dumps(obj))
    with pytest.raises(ValueError): reconcile(tmp_path, FP)
