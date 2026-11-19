import pytest
from modules.guardian_v1_activation_journal import create_journal, read_journal, advance_journal, JournalError
A = "a"*64
B = "b"*64

def test_create_and_read(tmp_path):
    p = tmp_path/"journal.json"
    out = create_journal(p, previous_sha256=A, candidate_sha256=B)
    assert out["state"] == "PREPARED" and not out["arm_authorized"]
    assert read_journal(p)["previous_sha256"] == A

def test_no_overwrite(tmp_path):
    p = tmp_path/"journal.json"
    create_journal(p, previous_sha256=A, candidate_sha256=B)
    with pytest.raises(JournalError): create_journal(p, previous_sha256=A, candidate_sha256=B)

def test_transitions(tmp_path):
    p = tmp_path/"journal.json"
    create_journal(p, previous_sha256=A, candidate_sha256=B)
    for a,b in [("PREPARED","BACKUP_VERIFIED"),("BACKUP_VERIFIED","REPLACEMENT_WRITTEN"),("REPLACEMENT_WRITTEN","VERIFIED")]:
        assert advance_journal(p, expected_state=a, next_state=b)["state"] == b
    with pytest.raises(JournalError): advance_journal(p, expected_state="VERIFIED", next_state="BACKUP_VERIFIED")

def test_stale_transition(tmp_path):
    p = tmp_path/"journal.json"
    create_journal(p, previous_sha256=A, candidate_sha256=B)
    with pytest.raises(JournalError): advance_journal(p, expected_state="BACKUP_VERIFIED", next_state="REPLACEMENT_WRITTEN")

def test_invalid_hash(tmp_path):
    with pytest.raises(JournalError): create_journal(tmp_path/"x", previous_sha256="bad", candidate_sha256=B)

def test_symlink_rejected(tmp_path):
    p = tmp_path/"journal.json"
    target = tmp_path/"target.json"; target.write_text("{}")
    p.symlink_to(target)
    with pytest.raises(JournalError): create_journal(p, previous_sha256=A, candidate_sha256=B)
    with pytest.raises(JournalError): read_journal(p)
