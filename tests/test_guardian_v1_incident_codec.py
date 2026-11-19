from copy import deepcopy

import pytest

from modules.guardian_types import (
    ProtectionTrigger,
    SafetyPowerResult,
    SessionState,
)
from modules.guardian_v1_incident_codec import (
    decode_incident,
    encode_incident,
)
from modules.guardian_v1_recovery_store import RecoveryStateError
from modules.protection_coordinator import initiate_protection


def make_incident(result=SafetyPowerResult.VERIFIED_OFF):
    return initiate_protection(
        triggers={ProtectionTrigger.ROOF_CLOSED},
        execute_action=lambda action: result,
    )


def test_incident_round_trip():
    original = make_incident()
    restored = decode_incident(encode_incident(original))

    assert restored.triggers == original.triggers
    assert restored.plan == original.plan
    assert restored.lost_capabilities == original.lost_capabilities
    assert restored.records == original.records
    assert restored.session_state is SessionState.ABORTED


def test_failed_attempts_and_retries_survive_round_trip():
    incident = make_incident(SafetyPowerResult.FAILED)

    assert len(incident.unresolved_actions) == 3

    initial_count = len(incident.records)
    incident.retry_unresolved(
        execute_action=lambda action: SafetyPowerResult.VERIFIED_OFF,
    )

    assert len(incident.records) == initial_count + 3
    assert incident.unresolved_actions == []

    restored = decode_incident(encode_incident(incident))
    assert restored.records == incident.records
    assert restored.unresolved_actions == []


@pytest.mark.parametrize("field,value", [
    ("triggers", []),
    ("triggers", ["UNKNOWN_TRIGGER"]),
    ("plan", []),
    ("plan", ["REQUEST_MOUNT_STOP"]),
    ("lost_capabilities", ["UNKNOWN_CAPABILITY"]),
    ("session_state", "DISARMED"),
    ("records", "invalid"),
])
def test_invalid_incident_fields_are_rejected(field, value):
    data = encode_incident(make_incident())
    data[field] = value

    with pytest.raises(RecoveryStateError):
        decode_incident(data)


def test_unknown_record_result_is_rejected():
    data = encode_incident(make_incident())
    data["records"][0]["result"] = "UNKNOWN_RESULT"

    with pytest.raises(RecoveryStateError):
        decode_incident(data)


def test_unexpected_record_action_is_rejected():
    data = encode_incident(make_incident())
    data["records"][0]["action"] = "REQUEST_MOUNT_STOP"

    with pytest.raises(RecoveryStateError):
        decode_incident(data)


def test_extra_incident_field_is_rejected():
    data = encode_incident(make_incident())
    data["unexpected"] = True

    with pytest.raises(RecoveryStateError):
        decode_incident(data)


def test_malformed_record_is_rejected():
    data = encode_incident(make_incident())
    data["records"][0] = {"action": "SAFETY_POWER_OFF_ASIAIR"}

    with pytest.raises(RecoveryStateError):
        decode_incident(data)
