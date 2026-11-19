import pytest
import yaml
from modules.guardian_v1_configuration_identity import (
    semantic_fingerprint, inspect_configuration_identity, ConfigurationIdentityError)
from modules.guardian_v1_setup_binding import MonitorBinding

BINDING = MonitorBinding('192.0.2.1', 'example.org', 443, 17, 5)

@pytest.fixture
def pair(tmp_path):
    data = {'asiair': {'ip_address': '192.0.2.1', 'timeout_seconds': 3},
            'roof': {'source': 'alpaca', 'alpaca_host': 'example.org', 'alpaca_port': 443,
                     'alpaca_device_number': 17}, 'monitor': {'interval_seconds': 5}}
    a, b = tmp_path/'config.yaml', tmp_path/'config.guardian-candidate.yaml'
    a.write_text(yaml.safe_dump(data))
    data['asiair']['timeout_seconds'] = 5
    b.write_text(yaml.safe_dump(data))
    return a, b

def test_semantic_identity_stable_for_order():
    assert semantic_fingerprint({'a': 1, 'b': {'x': 2}}) == semantic_fingerprint({'b': {'x': 2}, 'a': 1})

def test_identity_changes_with_setting():
    assert semantic_fingerprint({'a': 1}) != semantic_fingerprint({'a': 2})

def test_candidate_is_uncommissioned_and_files_untouched(pair):
    old = [p.read_bytes() for p in pair]
    result = inspect_configuration_identity(*pair, BINDING)
    assert result['active_identity'] != result['candidate_identity']
    assert result['changed_fields'] == ['asiair.timeout_seconds']
    assert result['commissioning_evidence_revalidation_required']
    assert result['active_matches_monitor_checked_fields']
    assert not result['runtime_identity_enforced']
    assert not result['activation_authorized']
    assert not result['commissioning_authorized']
    assert result['hardware_commands'] == 0
    assert old == [p.read_bytes() for p in pair]

def test_monitor_drift_not_authorized(pair):
    data = yaml.safe_load(pair[1].read_text())
    data['monitor']['interval_seconds'] = 10
    pair[1].write_text(yaml.safe_dump(data))
    result = inspect_configuration_identity(*pair, BINDING)
    assert not result['candidate_matches_monitor_checked_fields']
    assert not result['activation_authorized']

def test_structure_change_rejected(pair):
    data = yaml.safe_load(pair[1].read_text())
    data['new'] = {'setting': 1}
    pair[1].write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationIdentityError):
        inspect_configuration_identity(*pair, BINDING)

def test_same_file_rejected(pair):
    with pytest.raises(ConfigurationIdentityError):
        inspect_configuration_identity(pair[0], pair[0], BINDING)

def test_invalid_numeric_identity_rejected():
    with pytest.raises(ConfigurationIdentityError):
        semantic_fingerprint({'bad': float('nan')})
