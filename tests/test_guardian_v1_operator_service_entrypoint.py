"""Safe v1 operator service entrypoint checks."""
import pytest
import guardian_v1

def test_operator_service_requires_explicit_paths(monkeypatch):
    monkeypatch.setattr("sys.argv", ["guardian_v1.py", "--operator-service"])
    with pytest.raises(SystemExit, match="requires --recovery-file"):
        guardian_v1.main()

def test_operator_service_remains_monitor_only(tmp_path, monkeypatch):
    recovery = tmp_path / "missing.json"
    socket_dir = tmp_path / "socket"
    socket_dir.mkdir(mode=0o700)
    path = socket_dir / "operator.sock"
    class StopAfterOne:
        def __init__(self, app, socket_path):
            assert app.mode.hardware_execution_enabled is False
            assert app.supervisor.recovery_blocked is True
            assert str(socket_path) == str(path)
        def start(self): pass
        def serve_once(self): raise KeyboardInterrupt
        def close(self): pass
    monkeypatch.setattr("modules.guardian_v1_operator_socket.GuardianOperatorSocket", StopAfterOne)
    monkeypatch.setattr("sys.argv", ["guardian_v1.py", "--operator-service",
                                    "--recovery-file", str(recovery),
                                    "--operator-socket", str(path)])
    guardian_v1.main()
    assert not recovery.exists()
