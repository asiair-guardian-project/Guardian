import pytest
from modules.guardian_v1_setup_binding import MonitorBinding, compare_monitor_binding
from modules.guardian_v1_setup_config import SetupValidationError


@pytest.fixture
def active():
    return MonitorBinding('192.0.2.1', '192.0.2.2', 11111, 17, 5.0)


@pytest.fixture
def config():
    return {'asiair': {'ip_address': '192.0.2.1'},
            'roof': {'source': 'alpaca', 'alpaca_host': '192.0.2.2',
                     'alpaca_port': 11111, 'alpaca_device_number': 17},
            'monitor': {'interval_seconds': 5}}


def test_matching_config_is_still_not_authorized(config, active):
    result = compare_monitor_binding(config, active)
    assert result['matches_active_monitor']
    assert not result['safe_to_auto_apply']
    assert not result['commissioning_authorized']


@pytest.mark.parametrize('section,field,new', [
    ('asiair', 'ip_address', '192.0.2.99'),
    ('roof', 'alpaca_host', '192.0.2.99'),
    ('roof', 'alpaca_port', 1000),
    ('roof', 'alpaca_device_number', 3),
    ('monitor', 'interval_seconds', 10),
    ('roof', 'source', 'file'),
])
def test_mismatch_fails_closed(config, active, section, field, new):
    config[section][field] = new
    result = compare_monitor_binding(config, active)
    assert not result['matches_active_monitor']
    assert not result['safe_to_auto_apply']
    assert not result['commissioning_authorized']
    assert str(new) not in str(result)


def test_missing_field_fails_closed(config, active):
    del config['roof']['alpaca_host']
    assert not compare_monitor_binding(config, active)['matches_active_monitor']


def test_bad_config_fails_closed(active):
    with pytest.raises(SetupValidationError):
        compare_monitor_binding([], active)


def test_boolean_not_accepted_as_port(config, active):
    config['roof']['alpaca_port'] = True
    assert not compare_monitor_binding(config, active)['matches_active_monitor']
