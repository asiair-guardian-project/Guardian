import hashlib
from pathlib import Path
import pytest
import yaml
from modules.guardian_v1_activation_backup import prepare_activation_backup, ActivationBackupError


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path):
    a, c, b = [tmp_path / x for x in ('config.yaml', 'candidate.yaml', 'backup.yaml')]
    original = {'asiair': {'timeout_seconds': 3, 'ip_address': '192.168.1.2'}, 'roof': {'source': 'alpaca'}}
    proposed = {'asiair': {'timeout_seconds': 5, 'ip_address': '192.168.1.2'}, 'roof': {'source': 'alpaca'}}
    a.write_text(yaml.safe_dump(original)); c.write_text(yaml.safe_dump(proposed))
    return a, c, b


def run(a, c, b, **kwargs):
    return prepare_activation_backup(a, c, b, expected_active_sha256=kwargs.get('active', sha(a)), expected_candidate_sha256=kwargs.get('candidate', sha(c)))


def test_backup_preserves_active_and_candidate(tmp_path):
    a, c, b = fixture(tmp_path)
    old, proposed = a.read_bytes(), c.read_bytes()
    result = run(a, c, b)
    assert b.read_bytes() == old and a.read_bytes() == old and c.read_bytes() == proposed
    assert result['changed_fields'] == ['asiair.timeout_seconds']
    assert not result['activated'] and not result['commissioning_authorized']
    assert b.stat().st_mode & 0o777 == 0o600


def test_stale_active_rejected(tmp_path):
    a, c, b = fixture(tmp_path)
    with pytest.raises(ActivationBackupError, match='changed'):
        run(a, c, b, active='0' * 64)
    assert not b.exists()


def test_stale_candidate_rejected(tmp_path):
    a, c, b = fixture(tmp_path)
    with pytest.raises(ActivationBackupError, match='changed'):
        run(a, c, b, candidate='0' * 64)
    assert not b.exists()


def test_backup_not_overwritten(tmp_path):
    a, c, b = fixture(tmp_path)
    b.write_text('preserve')
    with pytest.raises(ActivationBackupError, match='exists'):
        run(a, c, b)
    assert b.read_text() == 'preserve'


def test_unapproved_field_rejected(tmp_path):
    a, c, b = fixture(tmp_path)
    content = yaml.safe_load(c.read_text())
    content['asiair']['unsupported'] = 'x'
    c.write_text(yaml.safe_dump(content))
    with pytest.raises(ActivationBackupError, match='structure'):
        run(a, c, b)
    assert not b.exists()


def test_symlink_rejected(tmp_path):
    a, c, b = fixture(tmp_path)
    link = tmp_path / 'link.yaml'
    link.symlink_to(a)
    with pytest.raises(ActivationBackupError, match='Symlink'):
        run(link, c, b)


def test_different_directory_rejected(tmp_path):
    a, c, b = fixture(tmp_path)
    elsewhere = tmp_path / 'other'; elsewhere.mkdir()
    with pytest.raises(ActivationBackupError, match='sibling'):
        run(a, c, elsewhere / 'backup.yaml')


def test_no_change_rejected(tmp_path):
    a, c, b = fixture(tmp_path)
    c.write_bytes(a.read_bytes())
    with pytest.raises(ActivationBackupError, match='no changes'):
        run(a, c, b)
