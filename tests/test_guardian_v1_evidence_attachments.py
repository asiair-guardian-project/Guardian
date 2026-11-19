import hashlib
import pytest
from guardian_v1_evidence_attachments import make_manifest
from modules.commissioning import CommissioningCheck

FINGERPRINT = "a" * 64

def test_empty_inventory_never_authorizes():
    result = make_manifest(FINGERPRINT, {})
    assert set(result["checks"]) == {c.name for c in CommissioningCheck}
    assert result["verified_count"] == 0
    assert result["commissioned"] is False
    assert result["hardware_authorized"] is False
    assert all(v["commissioning_result"] == "NOT_TESTED" for v in result["checks"].values())

def test_attached_file_is_hashed_but_not_verified(tmp_path):
    file = tmp_path / "historical-output.txt"
    file.write_bytes(b"VERIFIED_OFF historical result")
    result = make_manifest(FINGERPRINT, {"ASIAIR_SAFETY_POWER": [file]})
    entry = result["checks"]["ASIAIR_SAFETY_POWER"]
    assert entry["attachments"][0]["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    assert entry["attachments"][0]["reviewed"] is False
    assert entry["commissioning_result"] == "NOT_TESTED"

def test_invalid_check_and_missing_file_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        make_manifest(FINGERPRINT, {"BAD_CHECK": []})
    with pytest.raises(FileNotFoundError):
        make_manifest(FINGERPRINT, {"MOUNT_SAFETY_POWER": [tmp_path / "missing"]})

def test_invalid_fingerprint_fails_closed():
    with pytest.raises(ValueError):
        make_manifest("wrong", {})
