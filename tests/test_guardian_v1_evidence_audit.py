import plistlib
import pytest
from guardian_v1_evidence_audit import audit

def make_plist(path):
    argv = ["python", "guardian_v1.py", "--continuous-monitor"]
    for key, value in [("--recovery-file", "/tmp/state.json"), ("--operator-socket", "/tmp/op.sock"),
                       ("--asiair-host", "192.168.1.20"), ("--alpaca-host", "alpaca-api.tx.starfront.space"),
                       ("--alpaca-port", "443"), ("--alpaca-device", "17")]:
        argv += [key, value]
    path.write_bytes(plistlib.dumps({"ProgramArguments": argv, "RunAtLoad": True, "KeepAlive": False}))

def test_audit_is_stable_and_fail_closed(tmp_path):
    plist = tmp_path / "agent.plist"
    make_plist(plist)
    one = audit(plist, "192.168.1.30")
    two = audit(plist, "192.168.1.30")
    assert one == two
    assert not one["hardware_authorized"]
    assert not one["commissioned"]
    assert one["execution_commands"] == 0
    assert {v["outlet"] for v in one["configuration"]["targets"].values()} == {2, 3, 4}
    assert len(one["checks"]) == 8

def test_configuration_change_invalidates_fingerprint(tmp_path):
    plist = tmp_path / "agent.plist"
    make_plist(plist)
    assert audit(plist, "192.168.1.30")["configuration_fingerprint_sha256"] != audit(plist, "192.168.1.31")["configuration_fingerprint_sha256"]

def test_empty_host_rejected(tmp_path):
    plist = tmp_path / "agent.plist"
    make_plist(plist)
    with pytest.raises(ValueError):
        audit(plist, "")
