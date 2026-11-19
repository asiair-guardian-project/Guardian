import os
import pytest
import yaml
from modules.guardian_v1_setup_staging import (
    StagingError, configuration_sha256, stage_configuration,
)


@pytest.fixture
def installation(tmp_path):
    active = tmp_path / 'config.yaml'
    active.write_text(yaml.safe_dump({
        'asiair': {'ip_address': '192.0.2.1', 'timeout_seconds': 5},
        'roof': {'source': 'alpaca', 'alpaca_host': 'example.org',
                 'alpaca_port': 443, 'alpaca_device_number': 17,
                 'stale_after_seconds': 30},
        'monitor': {'interval_seconds': 5},
        'kasa': {'power_strip_ip': '192.0.2.3'},
        'custom': {'preserve': 'yes'},
    }), encoding='utf-8')
    return active


def test_stage_preserves_active_and_unrelated_fields(installation):
    before = installation.read_bytes()
    dest = installation.with_name('config.candidate.yaml')
    result = stage_configuration(installation, {'asiair': {'timeout_seconds': 8}},
                                 expected_sha256=configuration_sha256(installation), destination=dest)
    assert result['staged'] and not result['activated'] and not result['commissioning_authorized']
    assert installation.read_bytes() == before
    staged = yaml.safe_load(dest.read_text())
    assert staged['asiair']['timeout_seconds'] == 8
    assert staged['custom']['preserve'] == 'yes'
    assert os.stat(dest).st_mode & 0o077 == 0


def test_stale_review_rejected(installation):
    old = configuration_sha256(installation)
    installation.write_text(installation.read_text() + '\n# changed\n')
    with pytest.raises(StagingError, match='changed'):
        stage_configuration(installation, {'asiair': {'timeout_seconds': 8}},
                            expected_sha256=old, destination=installation.with_name('candidate.yaml'))
    assert not installation.with_name('candidate.yaml').exists()


def test_no_overwrite_or_active_replacement(installation):
    digest = configuration_sha256(installation)
    dest = installation.with_name('candidate.yaml')
    dest.write_text('existing')
    for target in (dest, installation, installation.parent.parent / 'outside.yaml'):
        with pytest.raises(StagingError):
            stage_configuration(installation, {'asiair': {'timeout_seconds': 8}},
                                expected_sha256=digest, destination=target)
    assert dest.read_text() == 'existing'


def test_rejects_unsupported_hardware_fields(installation):
    with pytest.raises(ValueError):
        stage_configuration(installation, {'wave': {'host': '192.0.2.7'}},
                            expected_sha256=configuration_sha256(installation),
                            destination=installation.with_name('candidate.yaml'))
    assert not installation.with_name('candidate.yaml').exists()
