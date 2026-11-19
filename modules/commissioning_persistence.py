"""Guardian 1.0 commissioning audit persistence."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
)
from modules.commissioning_audit import (
    CommissioningAuditEntry,
    CommissioningAuditRecord,
)


SCHEMA_VERSION = 1


class CommissioningPersistenceError(ValueError):
    """Raised when persisted commissioning data is invalid."""


def _validate_json_value(value: Any) -> None:
    """Require observations to contain JSON-compatible values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return

    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CommissioningPersistenceError(
                    "observation keys must be strings"
                )
            _validate_json_value(item)
        return

    raise CommissioningPersistenceError(
        f"unsupported observation value: {type(value).__name__}"
    )


def audit_record_to_dict(
    record: CommissioningAuditRecord,
) -> dict[str, Any]:
    """Convert an audit record to versioned JSON-compatible data."""

    if not record.configuration_fingerprint:
        raise CommissioningPersistenceError(
            "configuration fingerprint must not be empty"
        )

    entries = []

    for entry in record.entries:
        observations = dict(entry.observations)
        _validate_json_value(observations)

        entries.append(
            {
                "check": entry.check.name,
                "result": entry.result.name,
                "observed_at": entry.observed_at.isoformat(),
                "summary": entry.summary,
                "observations": observations,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "configuration_fingerprint": record.configuration_fingerprint,
        "entries": entries,
    }


def audit_record_from_dict(
    data: Any,
) -> CommissioningAuditRecord:
    """Parse and validate persisted commissioning audit data."""

    if not isinstance(data, dict):
        raise CommissioningPersistenceError(
            "commissioning audit document must be an object"
        )

    if data.get("schema_version") != SCHEMA_VERSION:
        raise CommissioningPersistenceError(
            "unsupported commissioning audit schema version"
        )

    fingerprint = data.get("configuration_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise CommissioningPersistenceError(
            "configuration fingerprint must not be empty"
        )

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise CommissioningPersistenceError(
            "commissioning audit entries must be a list"
        )

    entries = []
    seen: set[CommissioningCheck] = set()

    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise CommissioningPersistenceError(
                "commissioning audit entry must be an object"
            )

        try:
            check = CommissioningCheck[raw["check"]]
            result = CommissioningResult[raw["result"]]
        except (KeyError, TypeError):
            raise CommissioningPersistenceError(
                "invalid commissioning check or result"
            ) from None

        if check in seen:
            raise CommissioningPersistenceError(
                f"duplicate commissioning check: {check.name}"
            )
        seen.add(check)

        observed_at_raw = raw.get("observed_at")
        if not isinstance(observed_at_raw, str):
            raise CommissioningPersistenceError(
                "observed_at must be an ISO timestamp"
            )

        try:
            observed_at = datetime.fromisoformat(observed_at_raw)
        except ValueError:
            raise CommissioningPersistenceError(
                "observed_at must be an ISO timestamp"
            ) from None

        if observed_at.tzinfo is None:
            raise CommissioningPersistenceError(
                "observed_at must be timezone-aware"
            )

        summary = raw.get("summary")
        if not isinstance(summary, str):
            raise CommissioningPersistenceError(
                "summary must be a string"
            )

        observations = raw.get("observations")
        if not isinstance(observations, dict):
            raise CommissioningPersistenceError(
                "observations must be an object"
            )
        _validate_json_value(observations)

        entries.append(
            CommissioningAuditEntry(
                check=check,
                result=result,
                observed_at=observed_at,
                summary=summary,
                observations=dict(observations),
            )
        )

    return CommissioningAuditRecord(
        configuration_fingerprint=fingerprint,
        entries=tuple(entries),
    )


def save_commissioning_audit(
    path: str | Path,
    record: CommissioningAuditRecord,
) -> None:
    """Persist a commissioning audit record as versioned JSON."""

    target = Path(path)
    data = audit_record_to_dict(record)
    encoded = (
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())

        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_commissioning_audit(
    path: str | Path,
) -> CommissioningAuditRecord:
    """Load and validate a persisted commissioning audit record."""

    source = Path(path)

    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommissioningPersistenceError(
            f"unable to load commissioning audit: {exc}"
        ) from exc

    return audit_record_from_dict(data)
