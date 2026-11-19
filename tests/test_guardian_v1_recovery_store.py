import json

import pytest

from modules.guardian_v1_recovery_store import (
    GuardianV1RecoveryStore,
    RecoveryStateError,
)


def clean_state():
    return {
        "schema_version": 2,
        "active_incident": None,
        "abort_acknowledged": False,
        "incident_history": [],
        "session_state": "DISARMED",
        "shutdown_clean": True,
        "recovery_required": False,
    }


def test_recovery_state_round_trip(tmp_path):
    store = GuardianV1RecoveryStore(tmp_path / "guardian_v1_recovery.json")
    state = clean_state()

    store.write(state)

    assert store.read() == state


def test_missing_recovery_state_fails_closed(tmp_path):
    store = GuardianV1RecoveryStore(tmp_path / "missing.json")

    with pytest.raises(RecoveryStateError):
        store.read()


def test_corrupt_recovery_state_is_rejected(tmp_path):
    path = tmp_path / "recovery.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(path).read()


@pytest.mark.parametrize("change", [
    {"schema_version": 1},
    {"schema_version": True},
    {"abort_acknowledged": "yes"},
    {"abort_acknowledged": True},
    {"incident_history": {}},
    {"active_incident": []},
])
def test_invalid_recovery_envelope_is_rejected(tmp_path, change):
    state = clean_state()
    state.update(change)

    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")

    with pytest.raises(RecoveryStateError):
        store.write(state)


def test_unknown_recovery_fields_are_rejected(tmp_path):
    state = clean_state()
    state["unexpected"] = True

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(tmp_path / "recovery.json").write(state)


def test_recovery_write_replaces_existing_file(tmp_path):
    path = tmp_path / "recovery.json"
    store = GuardianV1RecoveryStore(path)

    store.write(clean_state())

    updated = clean_state()
    updated["incident_history"] = [serialized_incident()]
    store.write(updated)

    assert json.loads(path.read_text(encoding="utf-8")) == updated
    assert store.read() == updated

def serialized_incident():
    from modules.guardian_types import ProtectionTrigger, SafetyPowerResult
    from modules.guardian_v1_incident_codec import encode_incident
    from modules.protection_coordinator import initiate_protection

    incident = initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )
    return encode_incident(incident)


def test_invalid_active_incident_is_rejected(tmp_path):
    state = clean_state()
    state["active_incident"] = {"invalid": True}

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(tmp_path / "recovery.json").write(state)


def test_invalid_incident_history_is_rejected(tmp_path):
    state = clean_state()
    state["incident_history"] = [{"invalid": True}]

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(tmp_path / "recovery.json").write(state)


def test_valid_active_incident_round_trip(tmp_path):
    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = clean_state()
    state["active_incident"] = serialized_incident()
    state["abort_acknowledged"] = True
    state["session_state"] = "ABORTED"
    state["shutdown_clean"] = False
    state["recovery_required"] = True

    store.write(state)

    assert store.read() == state


def test_invalid_incident_on_disk_is_rejected(tmp_path):
    path = tmp_path / "recovery.json"
    state = clean_state()
    state["active_incident"] = {"invalid": True}
    path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(path).read()


@pytest.mark.parametrize("change", [
    {"session_state": "INVALID"},
    {"shutdown_clean": "yes"},
    {"recovery_required": 1},
    {"session_state": "IMAGING_PERMITTED"},
    {"session_state": "ABORTED"},
    {"recovery_required": True},
])
def test_invalid_v2_recovery_combinations_are_rejected(tmp_path, change):
    state = clean_state()
    state.update(change)

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(tmp_path / "recovery.json").write(state)


def test_interrupted_imaging_state_is_preserved(tmp_path):
    store = GuardianV1RecoveryStore(tmp_path / "recovery.json")
    state = clean_state()
    state["session_state"] = "IMAGING_PERMITTED"
    state["shutdown_clean"] = False

    store.write(state)

    assert store.read() == state


def test_v1_recovery_file_is_rejected(tmp_path):
    path = tmp_path / "recovery.json"
    state = clean_state()
    state["schema_version"] = 1
    path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(RecoveryStateError):
        GuardianV1RecoveryStore(path).read()
