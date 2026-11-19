import pytest
import yaml
from modules.guardian_v1_activation_preflight import activation_preflight
from modules.guardian_v1_setup_binding import MonitorBinding

BINDING = MonitorBinding('192.0.2.1', 'example.org', 443, 17, 5)

@pytest.fixture
def files(tmp_path):
    data = {'asiair': {'ip_address': '192.0.2.1', 'timeout_seconds': 3},
            'roof': {'source': 'alpaca', 'alpaca_host': 'example.org', 'alpaca_port': 443,
                     'alpaca_device_number': 17}, 'monitor': {'interval_seconds': 5}}
    active = tmp_path / 'config.yaml'
    candidate = tmp_path / 'config.guardian-candidate.yaml'
    active.write_text(yaml.safe_dump(data))
    data['asiair']['timeout_seconds'] = 5
    candidate.write_text(yaml.safe_dump(data))
    return active, candidate

def test_diff_is_redacted_and_never_authorized(files):
    before = [p.read_bytes() for p in files]
    result = activation_preflight(*files, BINDING)
    assert result['changed_fields'] == ['asiair.timeout_seconds']
    assert result['matches_active_monitor_checked_fields']
    assert not result['activation_authorized']
    assert not result['commissioning_authorized']
    assert result['hardware_commands'] == 0
    assert before == [p.read_bytes() for p in files]

def test_monitor_mismatch_does_not_authorize(files):
    data = yaml.safe_load(files[1].read_text())
    data['monitor']['interval_seconds'] = 10
    files[1].write_text(yaml.safe_dump(data))
    result = activation_preflight(*files, BINDING)
    assert not result['matches_active_monitor_checked_fields']
    assert 'monitor.interval_seconds: differs from active launch' in result['monitor_differences']
    assert not result['activation_authorized']

def test_structure_changes_fail_closed(files):
    data = yaml.safe_load(files[1].read_text())
    data['new_section'] = {'value': 1}
    files[1].write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        activation_preflight(*files, BINDING)

def test_rejects_same_file(files):
    with pytest.raises(ValueError):
        activation_preflight(files[0], files[0], BINDING)
