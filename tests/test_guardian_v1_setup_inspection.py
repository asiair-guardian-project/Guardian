import yaml
from modules.guardian_v1_setup_binding import MonitorBinding
from modules.guardian_v1_setup_inspection import make_setup_provider


def test_inspection_redacts_values_and_never_authorizes(tmp_path):
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump({'asiair': {'ip_address': '192.0.2.1'},
        'roof': {'source': 'alpaca', 'alpaca_host': '192.0.2.2', 'alpaca_port': 11111,
                 'alpaca_device_number': 17}, 'monitor': {'interval_seconds': 5}}))
    inspect = make_setup_provider(path, MonitorBinding('192.0.2.1', '192.0.2.2', 11111, 17, 5))
    result = inspect()
    assert result['available'] and result['matches_active_monitor']
    assert not result['editable'] and not result['save_available']
    assert not result['commissioning_authorized']
    assert '192.0.2' not in str(result)
    path.write_text(path.read_text().replace('192.0.2.1', '192.0.2.9'))
    assert not inspect()['matches_active_monitor']
    path.unlink()
    assert not inspect()['available']
