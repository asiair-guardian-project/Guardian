from datetime import datetime, timezone

import pytest

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
    CommissioningResult,
    REQUIRED_COMMISSIONING_CHECKS,
)
from modules.commissioning_coordinator import assemble_commissioning_status


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def evidence_for(
    check: CommissioningCheck,
    *,
    passed: bool = True,
) -> CommissioningEvidence:
    return CommissioningEvidence(
        check=check,
        completed=True,
        passed=passed,
        observed_at=NOW,
        summary=f"{check.name} commissioning evidence",
        observations={},
    )


def test_complete_verified_evidence_commissions_configuration():
    status = assemble_commissioning_status(
        configuration_fingerprint="config-a",
        evidence=[
            evidence_for(check)
            for check in REQUIRED_COMMISSIONING_CHECKS
        ],
    )

    assert status.commissioned
    assert status.valid_for_configuration("config-a")
    assert not status.valid_for_configuration("config-b")
    assert status.unresolved_checks == frozenset()


def test_missing_evidence_remains_not_tested():
    missing = CommissioningCheck.PROTECTION_LOGIC

    status = assemble_commissioning_status(
        configuration_fingerprint="config-a",
        evidence=[
            evidence_for(check)
            for check in REQUIRED_COMMISSIONING_CHECKS
            if check is not missing
        ],
    )

    assert not status.commissioned
    assert status.result_for(missing) is CommissioningResult.NOT_TESTED
    assert status.unresolved_checks == frozenset({missing})


def test_failed_evidence_prevents_commissioning():
    failed = CommissioningCheck.MOUNT_SAFETY_POWER

    status = assemble_commissioning_status(
        configuration_fingerprint="config-a",
        evidence=[
            evidence_for(
                check,
                passed=check is not failed,
            )
            for check in REQUIRED_COMMISSIONING_CHECKS
        ],
    )

    assert not status.commissioned
    assert status.result_for(failed) is CommissioningResult.FAILED
    assert status.unresolved_checks == frozenset({failed})


def test_duplicate_evidence_is_rejected():
    item = evidence_for(CommissioningCheck.ASIAIR_MONITORING)

    with pytest.raises(
        ValueError,
        match="duplicate commissioning evidence",
    ):
        assemble_commissioning_status(
            configuration_fingerprint="config-a",
            evidence=[item, item],
        )


def test_empty_configuration_fingerprint_is_rejected():
    with pytest.raises(
        ValueError,
        match="configuration_fingerprint must not be empty",
    ):
        assemble_commissioning_status(
            configuration_fingerprint="",
            evidence=[],
        )
