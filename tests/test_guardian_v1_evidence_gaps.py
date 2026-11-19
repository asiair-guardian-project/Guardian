import plistlib
from guardian_v1_evidence_gaps import gap_report
from modules.commissioning import CommissioningCheck

def test_gap_report_is_read_only_and_complete(tmp_path):
    plist = tmp_path / "agent.plist"
    argv = ["python", "guardian_v1.py", "--continuous-monitor"]
    for key, value in [
        ("--recovery-file", "/tmp/state.json"),
        ("--operator-socket", "/tmp/op.sock"),
        ("--asiair-host", "192.168.1.20"),
        ("--alpaca-host", "alpaca-api.tx.starfront.space"),
        ("--alpaca-port", "443"), ("--alpaca-device", "17")
    ]:
        argv += [key, value]
    plist.write_bytes(plistlib.dumps({"ProgramArguments": argv, "RunAtLoad": True, "KeepAlive": False}))
    result = gap_report(plist, "192.168.1.30")
    assert result["commissioned"] is False
    assert result["hardware_authorized"] is False
    assert result["execution_commands"] == 0
    assert set(result["checks"]) == {c.name for c in CommissioningCheck}
    assert all(c["review_status"] == "PENDING" for c in result["checks"].values())
