import pytest
from modules.guardian_v1_setup_config import (
    SetupValidationError, read_installation, redacted_overview, validate_changes,
)


@pytest.fixture
def config():
    return {
        'asiair': {'ip_address': '192.0.2.4', 'timeout_seconds': 3},
        'roof': {'source': 'alpaca', 'alpaca_host': 'example.local',
                 'alpaca_port': 11111, 'alpaca_device_number': 0,
                 'alpaca_timeout_seconds': 3, 'stale_after_seconds': 30},
        'kasa': {'power_strip_ip': '192.0.2.8'},
        'monitor': {'interval_seconds': 5},
        'wave': {'host': '192.0.2.9'},
        'custom': {'keep': True},
    }


def test_read_only_load(tmp_path):
    file = tmp_path / 'config.yaml'
    file.write_text('asiair:\n  ip_address: 192.0.2.4\n')
    assert read_installation(file)['asiair']['ip_address'] == '192.0.2.4'
    assert file.read_text() == 'asiair:\n  ip_address: 192.0.2.4\n'


def test_preview_preserves_unrelated_fields_and_original(config):
    candidate = validate_changes(config, {'asiair': {'ip_address': '192.0.2.12'}})
    assert candidate['asiair']['ip_address'] == '192.0.2.12'
    assert config['asiair']['ip_address'] == '192.0.2.4'
    assert candidate['wave'] == config['wave']
    assert candidate['custom'] == config['custom']


@pytest.mark.parametrize('changes', [
    {'wave': {'host': 'example.local'}},
    {'kasa': {'outlets': [1, 2]}},
    {'asiair': {'ip_address': 'host:123'}},
    {'asiair': {'timeout_seconds': -1}},
    {'roof': {'alpaca_port': 99999}},
    {'roof': {'source': 'file'}},
    {'monitor': {'interval_seconds': True}},
    {'guardian': {'hardware_execution_enabled': True}},
])
def test_reject_unsafe_or_unrecognized_changes(config, changes):
    with pytest.raises(SetupValidationError):
        validate_changes(config, changes)


def test_overview_does_not_disclose_values(config):
    overview = redacted_overview(config)
    assert '192.0.2.4' not in str(overview)
    assert 'ip_address' in overview['asiair']
