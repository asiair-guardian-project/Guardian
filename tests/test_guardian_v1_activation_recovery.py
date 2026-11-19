import hashlib
import pytest
from modules.guardian_v1_activation_recovery import audit_activation_state, RecoveryAuditError

def sha(data): return hashlib.sha256(data).hexdigest()

def test_not_started(tmp_path):
    (tmp_path/'active').write_bytes(b'old')
    (tmp_path/'candidate').write_bytes(b'new')
    result = audit_activation_state(tmp_path/'active',tmp_path/'candidate',tmp_path/'backup',
                                    expected_previous_sha256=sha(b'old'),expected_candidate_sha256=sha(b'new'))
    assert result['state']=='NOT_STARTED' and not result['activation_authorized']

def test_backup_present(tmp_path):
    for name, data in [('active',b'old'),('candidate',b'new'),('backup',b'old')]:
        (tmp_path/name).write_bytes(data)
    result = audit_activation_state(*(tmp_path/name for name in ('active','candidate','backup')),
                                    expected_previous_sha256=sha(b'old'),expected_candidate_sha256=sha(b'new'))
    assert result['state']=='BACKUP_PRESENT_ACTIVE_UNCHANGED'
    assert result['requires_operator_review']

def test_replacement_still_requires_review(tmp_path):
    for name,data in [('active',b'new'),('candidate',b'new'),('backup',b'old')]:
        (tmp_path/name).write_bytes(data)
    result = audit_activation_state(*(tmp_path/name for name in ('active','candidate','backup')),
                                    expected_previous_sha256=sha(b'old'),expected_candidate_sha256=sha(b'new'))
    assert result['state']=='REPLACEMENT_ON_DISK_REQUIRES_RUNTIME_RECONCILIATION'
    assert not result['arm_authorized'] and not result['runtime_verified']

def test_changed_candidate_fails_closed(tmp_path):
    for name,data in [('active',b'old'),('candidate',b'other')]:
        (tmp_path/name).write_bytes(data)
    result = audit_activation_state(*(tmp_path/name for name in ('active','candidate','backup')),
                                    expected_previous_sha256=sha(b'old'),expected_candidate_sha256=sha(b'new'))
    assert result['state']=='CANDIDATE_MISSING_OR_CHANGED'

def test_symlink_rejected(tmp_path):
    (tmp_path/'active').write_bytes(b'old');(tmp_path/'candidate').symlink_to(tmp_path/'active')
    with pytest.raises(RecoveryAuditError,match='Symlink'):
        audit_activation_state(*(tmp_path/name for name in ('active','candidate','backup')),
                               expected_previous_sha256=sha(b'old'),expected_candidate_sha256=sha(b'new'))
