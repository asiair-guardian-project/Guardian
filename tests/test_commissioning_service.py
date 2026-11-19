from datetime import datetime, timezone

import pytest

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
    CommissioningResult,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.commissioning_service import CommissioningSession


def evidence(check, *, passed=True, completed=True):
    return CommissioningEvidence(
        check=check,
        completed=completed,
        passed=passed,
        observed_at=datetime.now(timezone.utc),
        summary="commissioning test evidence",
        observations={},
    )


def test_new_session_has_no_verified_evidence():
    session = CommissioningSession("config-a")
    status = session.status()

    assert not status.commissioned
    assert status.unresolved_checks == REQUIRED_COMMISSIONING_CHECKS
    assert status.configuration_fingerprint == "config-a"


def test_explicit_result_is_recorded():
    session = CommissioningSession("config-a")
    session.record_evidence(
        evidence(CommissioningCheck.ASIAIR_MONITORING)
    )

    status = session.status()

    assert (
        status.result_for(CommissioningCheck.ASIAIR_MONITORING)
        is CommissioningResult.VERIFIED
    )


def test_failed_result_remains_unresolved():
    session = CommissioningSession("config-a")
    session.record_evidence(
        evidence(
            CommissioningCheck.MOUNT_SAFETY_POWER,
            passed=False,
        )
    )

    status = session.status()

    assert (
        status.result_for(CommissioningCheck.MOUNT_SAFETY_POWER)
        is CommissioningResult.FAILED
    )
    assert CommissioningCheck.MOUNT_SAFETY_POWER in status.unresolved_checks


def test_all_explicit_verified_results_complete_commissioning():
    session = CommissioningSession("config-a")

    for check in REQUIRED_COMMISSIONING_CHECKS:
        session.record_evidence(evidence(check))

    status = session.status()

    assert status.commissioned
    assert status.valid_for_configuration("config-a")


def test_absent_evidence_remains_not_tested():
    session = CommissioningSession("config-a")

    assert (
        session.status().result_for(CommissioningCheck.PROTECTION_LOGIC)
        is CommissioningResult.NOT_TESTED
    )
    assert session.evidence_for(
        CommissioningCheck.PROTECTION_LOGIC
    ) is None


def test_empty_configuration_fingerprint_is_rejected():
    with pytest.raises(ValueError):
        CommissioningSession("")


def test_status_is_snapshot_not_live_view():
    session = CommissioningSession("config-a")
    first = session.status()

    session.record_evidence(
        evidence(CommissioningCheck.ASIAIR_MONITORING)
    )

    assert (
        first.result_for(CommissioningCheck.ASIAIR_MONITORING)
        is CommissioningResult.NOT_TESTED
    )


def test_evidence_is_retained_and_verified_result_is_derived():
    from datetime import datetime, timezone

    from modules.commissioning import CommissioningEvidence

    session = CommissioningSession("config-a")

    evidence = CommissioningEvidence(
        check=CommissioningCheck.ASIAIR_SAFETY_POWER,
        completed=True,
        passed=True,
        observed_at=datetime.now(timezone.utc),
        summary="ASIAIR power-off verified",
        observations={"power_result": "VERIFIED_OFF"},
    )

    session.record_evidence(evidence)

    assert session.evidence_for(
        CommissioningCheck.ASIAIR_SAFETY_POWER
    ) is evidence
    assert (
        session.status().result_for(
            CommissioningCheck.ASIAIR_SAFETY_POWER
        )
        is CommissioningResult.VERIFIED
    )


def test_failing_evidence_cannot_create_verified_result():
    from datetime import datetime, timezone

    from modules.commissioning import CommissioningEvidence

    session = CommissioningSession("config-a")

    evidence = CommissioningEvidence(
        check=CommissioningCheck.MOUNT_SAFETY_POWER,
        completed=True,
        passed=False,
        observed_at=datetime.now(timezone.utc),
        summary="Mount power-off verification failed",
        observations={"power_result": "FAILED"},
    )

    session.record_evidence(evidence)

    assert (
        session.status().result_for(
            CommissioningCheck.MOUNT_SAFETY_POWER
        )
        is CommissioningResult.FAILED
    )


def test_unrecorded_check_has_no_evidence():
    session = CommissioningSession("config-a")

    assert session.evidence_for(
        CommissioningCheck.PROTECTION_LOGIC
    ) is None


def test_session_has_no_direct_result_recording_api():
    session = CommissioningSession("config-a")

    assert not hasattr(session, "record")


def test_audit_record_preserves_commissioning_evidence():
    session = CommissioningSession("config-a")
    evidence = CommissioningEvidence(
        check=CommissioningCheck.ASIAIR_MONITORING,
        completed=True,
        passed=True,
        observed_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
        summary="ASIAIR monitoring verified",
        observations={
            "saw_reachable": True,
            "saw_unreachable": True,
        },
    )

    session.record_evidence(evidence)
    record = session.audit_record()
    entry = record.entry_for(CommissioningCheck.ASIAIR_MONITORING)

    assert record.configuration_fingerprint == "config-a"
    assert entry is not None
    assert entry.result is CommissioningResult.VERIFIED
    assert entry.observed_at == evidence.observed_at
    assert entry.summary == evidence.summary
    assert entry.observations == evidence.observations


def test_audit_record_contains_only_recorded_evidence():
    session = CommissioningSession("config-a")

    record = session.audit_record()

    assert record.entries == ()
    assert (
        record.entry_for(CommissioningCheck.PROTECTION_LOGIC)
        is None
    )
