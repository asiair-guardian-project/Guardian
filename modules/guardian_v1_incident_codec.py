"""Strict serialization of Guardian 1.0 protection incidents."""

from modules.guardian_types import (
    Capability,
    ProtectionAction,
    ProtectionTrigger,
    SafetyPowerResult,
    SessionState,
)
from modules.guardian_v1_recovery_store import RecoveryStateError
from modules.protection_coordinator import ProtectionIncident
from modules.protection_execution import ProtectionActionRecord
from modules.protection_planner import build_protection_plan


def _enum(enum_type, name):
    if not isinstance(name, str):
        raise RecoveryStateError("Enum name must be a string.")
    try:
        return enum_type[name]
    except KeyError as error:
        raise RecoveryStateError(
            f"Unknown {enum_type.__name__}: {name}"
        ) from error


def _enum_set(enum_type, names):
    if not isinstance(names, list):
        raise RecoveryStateError("Expected an enum list.")
    values = [_enum(enum_type, name) for name in names]
    if len(values) != len(set(values)):
        raise RecoveryStateError("Duplicate enum value.")
    return set(values)


def encode_incident(incident: ProtectionIncident) -> dict:
    """Encode and validate an incident before persistence."""
    data = {
        "triggers": sorted(x.name for x in incident.triggers),
        "plan": [x.name for x in incident.plan],
        "lost_capabilities": sorted(
            x.name for x in incident.lost_capabilities
        ),
        "records": [
            {"action": r.action.name, "result": r.result.name}
            for r in incident.records
        ],
        "session_state": incident.session_state.name,
    }
    decode_incident(data)
    return data


def decode_incident(data: dict) -> ProtectionIncident:
    """Reject malformed or inconsistent persisted incidents."""
    required = {
        "triggers",
        "plan",
        "lost_capabilities",
        "records",
        "session_state",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise RecoveryStateError("Invalid incident structure.")

    triggers = _enum_set(ProtectionTrigger, data["triggers"])
    lost = _enum_set(Capability, data["lost_capabilities"])

    if not triggers:
        raise RecoveryStateError("Incident requires a trigger.")

    if not isinstance(data["plan"], list):
        raise RecoveryStateError("Invalid protection plan.")

    plan = [_enum(ProtectionAction, x) for x in data["plan"]]
    if plan != build_protection_plan():
        raise RecoveryStateError("Invalid required shutdown plan.")

    if data["session_state"] != SessionState.ABORTED.name:
        raise RecoveryStateError("Incident must remain ABORTED.")

    if not isinstance(data["records"], list):
        raise RecoveryStateError("Invalid protection records.")

    records = []
    for item in data["records"]:
        if not isinstance(item, dict) or set(item) != {"action", "result"}:
            raise RecoveryStateError("Malformed protection record.")

        action = _enum(ProtectionAction, item["action"])
        if action not in plan:
            raise RecoveryStateError("Unexpected protection action.")

        result = _enum(SafetyPowerResult, item["result"])
        records.append(ProtectionActionRecord(action, result))

    return ProtectionIncident(
        triggers=triggers,
        plan=plan,
        lost_capabilities=lost,
        records=records,
        session_state=SessionState.ABORTED,
    )
