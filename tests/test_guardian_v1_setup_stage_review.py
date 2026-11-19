import yaml
from modules.guardian_v1_setup_binding import MonitorBinding
from modules.guardian_v1_setup_inspection import make_setup_provider


def test_stage_candidate_never_changes_active(tmp_path):
    active = tmp_path / 'config.yaml'
    active.write_text(yaml.safe_dump({'asiair': {'ip_address': '192.0.2.1', 'timeout_seconds': 5},
        'roof': {'source': 'alpaca', 'alpaca_host': 'example.org', 'alpaca_port': 443,
                 'alpaca_device_number': 17, 'stale_after_seconds': 30},
        'monitor': {'interval_seconds': 5}, 'kasa': {'power_strip_ip': '192.0.2.3'}}))
    original = active.read_bytes()
    provider = make_setup_provider(active, MonitorBinding('192.0.2.1', 'example.org', 443, 17, 5))
    digest = provider()['review_sha256']
    changes = {'asiair': {'timeout_seconds': 8}}
    assert provider.preview(changes)['ok']
    result = provider.stage(changes, digest)
    assert result['ok'] and result['staged'] and not result['activated']
    assert not result['commissioning_authorized']
    assert active.read_bytes() == original
    candidate = tmp_path / 'config.guardian-candidate.yaml'
    assert yaml.safe_load(candidate.read_text())['asiair']['timeout_seconds'] == 8
    assert not provider.stage(changes, digest)['ok']  # no overwrite


def test_stale_review_is_rejected(tmp_path):
    active = tmp_path / 'config.yaml'
    active.write_text(yaml.safe_dump({'asiair': {'timeout_seconds': 5}}))
    provider = make_setup_provider(active, MonitorBinding('192.0.2.1', 'example.org', 443, 17, 5))
    digest = provider()['review_sha256']
    active.write_text(active.read_text() + '# changed\n')
    result = provider.stage({'asiair': {'timeout_seconds': 8}}, digest)
    assert not result['ok']
    assert not (tmp_path / 'config.guardian-candidate.yaml').exists()
