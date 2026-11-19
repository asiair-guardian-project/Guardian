from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    CommissioningStatus,
    REQUIRED_COMMISSIONING_CHECKS,
)


def verified_results():
    return {
        check: CommissioningResult.VERIFIED
        for check in REQUIRED_COMMISSIONING_CHECKS
    }


def test_all_required_checks_verified_is_commissioned():
    status = CommissioningStatus(verified_results())

    assert status.commissioned
    assert status.unresolved_checks == frozenset()


def test_missing_check_is_not_tested_and_not_commissioned():
    results = verified_results()
    missing = CommissioningCheck.PROTECTION_LOGIC
    del results[missing]

    status = CommissioningStatus(results)

    assert status.result_for(missing) is CommissioningResult.NOT_TESTED
    assert not status.commissioned
    assert status.unresolved_checks == frozenset({missing})


def test_failed_check_prevents_commissioning():
    results = verified_results()
    failed = CommissioningCheck.MOUNT_SAFETY_POWER
    results[failed] = CommissioningResult.FAILED

    status = CommissioningStatus(results)

    assert not status.commissioned
    assert status.unresolved_checks == frozenset({failed})


def test_empty_status_is_not_commissioned():
    status = CommissioningStatus({})

    assert not status.commissioned
    assert status.unresolved_checks == REQUIRED_COMMISSIONING_CHECKS


def test_commissioning_is_valid_for_matching_configuration():
    status = CommissioningStatus(
        verified_results(),
        configuration_fingerprint="config-a",
    )

    assert status.valid_for_configuration("config-a")


def test_commissioning_is_not_valid_for_changed_configuration():
    status = CommissioningStatus(
        verified_results(),
        configuration_fingerprint="config-a",
    )

    assert status.commissioned
    assert not status.valid_for_configuration("config-b")


def test_commissioning_without_fingerprint_authorizes_no_configuration():
    status = CommissioningStatus(verified_results())

    assert status.commissioned
    assert not status.valid_for_configuration("config-a")


def test_completed_passing_evidence_is_verified():
    from datetime import datetime, timezone

    from modules.commissioning import (
        CommissioningEvidence,
        evaluate_commissioning_evidence,
    )

    evidence = CommissioningEvidence(
        check=CommissioningCheck.ASIAIR_SAFETY_POWER,
        completed=True,
        passed=True,
        observed_at=datetime.now(timezone.utc),
        summary="ASIAIR Safety Power shutdown verified",
        observations={"power_result": "VERIFIED_OFF"},
    )

    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


def test_completed_failing_evidence_is_failed():
    from datetime import datetime, timezone

    from modules.commissioning import (
        CommissioningEvidence,
        evaluate_commissioning_evidence,
    )

    evidence = CommissioningEvidence(
        check=CommissioningCheck.MOUNT_SAFETY_POWER,
        completed=True,
        passed=False,
        observed_at=datetime.now(timezone.utc),
        summary="Mount remained powered",
        observations={"power_result": "FAILED"},
    )

    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.FAILED
    )


def test_incomplete_evidence_cannot_verify_commissioning():
    from datetime import datetime, timezone

    from modules.commissioning import (
        CommissioningEvidence,
        evaluate_commissioning_evidence,
    )

    evidence = CommissioningEvidence(
        check=CommissioningCheck.PROTECTION_LOGIC,
        completed=False,
        passed=True,
        observed_at=datetime.now(timezone.utc),
        summary="Protection test did not complete",
        observations={},
    )

    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.FAILED
    )
