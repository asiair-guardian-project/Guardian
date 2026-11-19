from pathlib import Path
import hashlib
import pytest
from modules.guardian_v1_activation_startup_gate import assert_no_pending_activation, ActivationStartupBlocked
from modules.guardian_v1_activation_journal import create_journal, advance_journal


def test_clean_startup(tmp_path):
    assert assert_no_pending_activation(tmp_path / 'config.yaml') is True


def test_pending_prepared_blocks(tmp_path):
    p = tmp_path / 'config.guardian-activation-journal.json'
    create_journal(p, previous_sha256='a'*64, candidate_sha256='b'*64)
    with pytest.raises(ActivationStartupBlocked):
        assert_no_pending_activation(tmp_path / 'config.yaml')


def test_verified_still_blocks(tmp_path):
    p = tmp_path / 'config.guardian-activation-journal.json'
    create_journal(p, previous_sha256='a'*64, candidate_sha256='b'*64)
    for old,new in [('PREPARED','BACKUP_VERIFIED'),('BACKUP_VERIFIED','REPLACEMENT_WRITTEN'),('REPLACEMENT_WRITTEN','VERIFIED')]:
        advance_journal(p,expected_state=old,next_state=new)
    with pytest.raises(ActivationStartupBlocked):
        assert_no_pending_activation(tmp_path / 'config.yaml')


def test_corrupt_blocks(tmp_path):
    (tmp_path / 'config.guardian-activation-journal.json').write_text('{')
    with pytest.raises(ActivationStartupBlocked):
        assert_no_pending_activation(tmp_path / 'config.yaml')


def test_symlink_blocks(tmp_path):
    (tmp_path / 'target').write_text('')
    (tmp_path / 'config.guardian-activation-journal.json').symlink_to(tmp_path / 'target')
    with pytest.raises(ActivationStartupBlocked):
        assert_no_pending_activation(tmp_path / 'config.yaml')
