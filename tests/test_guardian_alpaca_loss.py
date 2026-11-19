import tempfile
from pathlib import Path
from modules.emergency_state_store import EmergencyStateStore
import modules.guardian as guardian_module
from modules.alpaca_safety_monitor import AlpacaSafetyMonitorError
from modules.guardian import Guardian


def failed_alpaca_read(*args, **kwargs):
    raise AlpacaSafetyMonitorError(
        "Simulated Alpaca communication failure"
    )


def configure_test_environment(monkeypatch):
    """Prevent dependence on real external hardware/services."""

    monkeypatch.setattr(
        guardian_module,
        "internet_available",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        guardian_module,
        "asiair_available",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        guardian_module,
        "read_wave_status",
        lambda: {
            "reachable": True,
            "axis1": {
                "status": "=TEST1",
                "position": "=AAAAAA",
            },
            "axis2": {
                "status": "=TEST2",
                "position": "=BBBBBB",
            },
        },
    )
    monkeypatch.setattr(
        guardian_module,
        "read_ups_status",
        lambda: {
            "power_source": "AC",
            "battery_percent": 100,
            "state": "TEST",
            "runtime": "TEST",
        },
    )
    monkeypatch.setattr(
        guardian_module,
        "read_alpaca_safety_status",
        failed_alpaca_read,
    )


def new_guardian():
    guardian = Guardian()
    guardian.config["roof"]["source"] = "alpaca"

    # Isolate emergency persistence from the production Guardian.
    guardian._test_directory = tempfile.TemporaryDirectory()
    guardian.emergency_state_store = EmergencyStateStore(
        Path(guardian._test_directory.name) / "emergency_state.json"
    )
    guardian.emergency_state_store.write({
        "schema_version": 1,
        "session_state": "DISARMED",
        "abort_reason": None,
        "operator_acknowledged": False,
        "emergency_retry_active": False,
        "protection_results": {},
    })
    assert guardian.restore_emergency_state()

    return guardian


def test_loss_while_waiting(monkeypatch):
    configure_test_environment(monkeypatch)
    guardian = new_guardian()

    protection_calls = []
    guardian.evaluate_protection = (
        lambda source, event_type:
        protection_calls.append((source, event_type))
    )

    guardian.start_session()
    guardian.monitor_once()

    assert (
        guardian.session.state
        == guardian.session.WAITING_FOR_ROOF
    )
    assert protection_calls == []

    print(
        "PASS: Alpaca loss while waiting does not permit imaging"
    )


def test_loss_while_imaging(monkeypatch):
    configure_test_environment(monkeypatch)
    guardian = new_guardian()

    protection_calls = []
    guardian.evaluate_protection = (
        lambda source, event_type:
        protection_calls.append((source, event_type))
    )

    guardian.start_session()
    assert guardian.session.permit_imaging()

    guardian.monitor_once()

    assert (
        guardian.session.state
        == guardian.session.IMAGING_PERMITTED
    )
    assert protection_calls == []

    print(
        "PASS: Alpaca loss while imaging does not abort "
        "or trigger emergency protection"
    )
