import plistlib
import pytest
from guardian_v1_commissioning_preflight import inspect_launchagent


def test_missing_monitor_flags_rejected(tmp_path):
    p = tmp_path / "a.plist"
    p.write_bytes(plistlib.dumps({"ProgramArguments": ["python"], "RunAtLoad": True, "KeepAlive": False}))
    with pytest.raises(ValueError, match="missing"):
        inspect_launchagent(p)


def test_valid_monitor_args(tmp_path):
    p = tmp_path / "a.plist"
    args = ["python", "guardian_v1.py", "--continuous-monitor"]
    for k, v in [("--recovery-file", "/tmp/recovery.json"), ("--operator-socket", "/tmp/op.sock"),
                 ("--asiair-host", "example.invalid"), ("--alpaca-host", "alpaca.invalid"),
                 ("--alpaca-port", "443"), ("--alpaca-device", "17")]:
        args.extend([k, v])
    p.write_bytes(plistlib.dumps({"ProgramArguments": args, "RunAtLoad": True, "KeepAlive": False}))
    assert inspect_launchagent(p)["--alpaca-port"] == "443"
