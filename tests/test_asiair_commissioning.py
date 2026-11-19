from datetime import datetime, timedelta, timezone

import pytest

from modules.asiair_commissioning import (
    AsiairMonitoringObservation,
    evaluate_asiair_monitoring_commissioning,
)
from modules.commissioning import (
    CommissioningCheck,
    evaluate_commissioning_evidence,
    CommissioningResult,
)


NOW = datetime.now(timezone.utc)


def observation(reachable, seconds=0):
    return AsiairMonitoringObservation(
        reachable=reachable,
        observed_at=NOW + timedelta(seconds=seconds),
    )


def test_reachable_and_unreachable_states_verify_monitoring():
    evidence = evaluate_asiair_monitoring_commissioning(
        (
            observation(False),
            observation(True, 1),
        )
    )

    assert evidence.check is CommissioningCheck.ASIAIR_MONITORING
    assert evidence.passed
    assert evidence.observations["saw_reachable"] is True
    assert evidence.observations["saw_unreachable"] is True
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.VERIFIED
    )


def test_only_reachable_state_does_not_verify_monitoring():
    evidence = evaluate_asiair_monitoring_commissioning(
        (
            observation(True),
            observation(True, 1),
        )
    )

    assert not evidence.passed
    assert (
        evaluate_commissioning_evidence(evidence)
        is CommissioningResult.FAILED
    )


def test_only_unreachable_state_does_not_verify_monitoring():
    evidence = evaluate_asiair_monitoring_commissioning(
        (
            observation(False),
            observation(False, 1),
        )
    )

    assert not evidence.passed


def test_empty_observations_are_rejected():
    with pytest.raises(ValueError):
        evaluate_asiair_monitoring_commissioning(())
