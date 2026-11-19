from datetime import datetime, timezone

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
)
from modules.commissioning_audit import (
    CommissioningAuditEntry,
    CommissioningAuditRecord,
)


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def entry(check, result=CommissioningResult.VERIFIED):
    return CommissioningAuditEntry(
        check=check,
        result=result,
        observed_at=NOW,
        summary="commissioning evidence",
        observations={},
    )


def test_audit_record_reconstructs_commissioning_status():
    record = CommissioningAuditRecord(
        configuration_fingerprint="config-a",
        entries=tuple(
            entry(check)
            for check in CommissioningCheck
        ),
    )

    status = record.status()

    assert status.commissioned
    assert status.valid_for_configuration("config-a")
    assert not status.valid_for_configuration("config-b")


def test_incomplete_audit_record_does_not_become_commissioned():
    record = CommissioningAuditRecord(
        configuration_fingerprint="config-a",
        entries=(
            entry(CommissioningCheck.ASIAIR_MONITORING),
        ),
    )

    status = record.status()

    assert not status.commissioned
    assert not status.valid_for_configuration("config-a")
