"""Continuous monitor CLI wiring, without real network or hardware."""
import sys
import pytest
import guardian_v1


def test_requires_explicit_inputs(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["guardian_v1.py", "--continuous-monitor"])
    with pytest.raises(SystemExit, match="requires"):
        guardian_v1.main()


def test_rejects_nonpositive_interval(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["guardian_v1.py", "--continuous-monitor",
        "--recovery-file", str(tmp_path / "missing.json"),
        "--operator-socket", str(tmp_path / "operator.sock"),
        "--asiair-host", "192.0.2.1", "--alpaca-host", "192.0.2.2",
        "--alpaca-port", "11111", "--cycle-seconds", "0"])
    with pytest.raises(SystemExit, match="positive"):
        guardian_v1.main()


def test_continuous_monitor_single_application(monkeypatch, tmp_path):
    import modules.guardian_v1_starfront_composition as comp
    import modules.guardian_v1_unified_runtime as unified
    seen = {}
    def compose(**kwargs):
        seen["app"] = kwargs["application"]
        return object()
    class Runner:
        def __init__(self, *, application, observation_runtime, socket_path, interval_seconds):
            assert application is seen["app"]
            assert not application.mode.hardware_execution_enabled
            assert application.supervisor.recovery_blocked
            assert interval_seconds == 5.0
        def run(self): seen["ran"] = True
    monkeypatch.setattr(comp, "compose_starfront_read_only", compose)
    monkeypatch.setattr(unified, "GuardianV1UnifiedRuntime", Runner)
    monkeypatch.setattr(sys, "argv", ["guardian_v1.py", "--continuous-monitor",
        "--recovery-file", str(tmp_path / "missing.json"),
        "--operator-socket", str(tmp_path / "operator.sock"),
        "--asiair-host", "192.0.2.1", "--alpaca-host", "192.0.2.2",
        "--alpaca-port", "11111"])
    guardian_v1.main()
    assert seen["ran"]
