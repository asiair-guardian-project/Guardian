from datetime import datetime, timezone
import json

import pytest

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
)
from modules.commissioning_audit import (
    CommissioningAuditEntry,
    CommissioningAuditRecord,
)
from modules.commissioning_persistence import (
    CommissioningPersistenceError,
    load_commissioning_audit,
    save_commissioning_audit,
)


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def record():
    return CommissioningAuditRecord(
        configuration_fingerprint="config-a",
        entries=(
            CommissioningAuditEntry(
                check=CommissioningCheck.ASIAIR_MONITORING,
                result=CommissioningResult.VERIFIED,
                observed_at=NOW,
                summary="ASIAIR monitoring verified",
                observations={
                    "saw_reachable": True,
                    "saw_unreachable": True,
                },
            ),
        ),
    )


def test_audit_record_round_trip(tmp_path):
    path = tmp_path / "commissioning.json"

    save_commissioning_audit(path, record())
    loaded = load_commissioning_audit(path)

    assert loaded == record()
    assert not loaded.status().commissioned
    assert not loaded.status().valid_for_configuration("config-a")
    assert not loaded.status().valid_for_configuration("config-b")


def test_unknown_schema_version_is_rejected(tmp_path):
    path = tmp_path / "commissioning.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "configuration_fingerprint": "config-a",
                "entries": [],
            }
        )
    )

    with pytest.raises(
        CommissioningPersistenceError,
        match="schema version",
    ):
        load_commissioning_audit(path)


def test_duplicate_checks_are_rejected(tmp_path):
    path = tmp_path / "commissioning.json"

    save_commissioning_audit(path, record())
    data = json.loads(path.read_text())
    data["entries"].append(dict(data["entries"][0]))
    path.write_text(json.dumps(data))

    with pytest.raises(
        CommissioningPersistenceError,
        match="duplicate commissioning check",
    ):
        load_commissioning_audit(path)


def test_naive_timestamp_is_rejected(tmp_path):
    path = tmp_path / "commissioning.json"

    save_commissioning_audit(path, record())
    data = json.loads(path.read_text())
    data["entries"][0]["observed_at"] = "2026-10-04T12:00:00"
    path.write_text(json.dumps(data))

    with pytest.raises(
        CommissioningPersistenceError,
        match="timezone-aware",
    ):
        load_commissioning_audit(path)


def test_malformed_json_is_rejected(tmp_path):
    path = tmp_path / "commissioning.json"
    path.write_text("{not-json")

    with pytest.raises(
        CommissioningPersistenceError,
        match="unable to load",
    ):
        load_commissioning_audit(path)


def test_complete_audit_record_retains_configuration_authorization(
    tmp_path,
):
    path = tmp_path / "commissioning.json"

    complete_record = CommissioningAuditRecord(
        configuration_fingerprint="config-a",
        entries=tuple(
            CommissioningAuditEntry(
                check=check,
                result=CommissioningResult.VERIFIED,
                observed_at=NOW,
                summary=f"{check.name} verified",
                observations={},
            )
            for check in CommissioningCheck
        ),
    )

    save_commissioning_audit(path, complete_record)
    loaded = load_commissioning_audit(path)
    status = loaded.status()

    assert loaded == complete_record
    assert status.commissioned
    assert status.valid_for_configuration("config-a")
    assert not status.valid_for_configuration("config-b")


def test_failed_atomic_replace_preserves_original_and_cleans_temp(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "commissioning.json"
    original = "original commissioning record\n"
    path.write_text(original)

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(
        "modules.commissioning_persistence.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="simulated replace failure"):
        save_commissioning_audit(path, record())

    assert path.read_text() == original
    assert list(tmp_path.glob(".commissioning.json.*.tmp")) == []
