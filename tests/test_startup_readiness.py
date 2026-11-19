from datetime import datetime, timezone

from modules.capability_model import REQUIRED_CAPABILITIES
from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
)
from modules.commissioning_audit import (
    CommissioningAuditEntry,
    CommissioningAuditRecord,
)
from modules.commissioning_persistence import save_commissioning_audit
from modules.guardian_types import Capability, CapabilityStatus
from modules.startup_readiness import evaluate_startup_readiness


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def available_capabilities():
    return {
        capability: CapabilityStatus.AVAILABLE
        for capability in REQUIRED_CAPABILITIES
    }


def commissioned_record(fingerprint="config-a"):
    return CommissioningAuditRecord(
        configuration_fingerprint=fingerprint,
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


def test_valid_persisted_commissioning_restores_readiness(tmp_path):
    path = tmp_path / "commissioning.json"
    save_commissioning_audit(path, commissioned_record())

    result = evaluate_startup_readiness(
        audit_path=path,
        configuration_fingerprint="config-a",
        capability_statuses=available_capabilities(),
    )

    assert result.ready
    assert result.commissioning_valid
    assert result.unavailable_capabilities == frozenset()
    assert result.audit_error is None


def test_configuration_change_invalidates_saved_commissioning(tmp_path):
    path = tmp_path / "commissioning.json"
    save_commissioning_audit(path, commissioned_record("config-a"))

    result = evaluate_startup_readiness(
        audit_path=path,
        configuration_fingerprint="config-b",
        capability_statuses=available_capabilities(),
    )

    assert not result.ready
    assert not result.commissioning_valid
    assert result.audit_error is None


def test_required_capability_loss_blocks_ready(tmp_path):
    path = tmp_path / "commissioning.json"
    save_commissioning_audit(path, commissioned_record())

    capabilities = available_capabilities()
    capabilities[Capability.SAFETY_POWER_CONTROL] = CapabilityStatus.FAILED

    result = evaluate_startup_readiness(
        audit_path=path,
        configuration_fingerprint="config-a",
        capability_statuses=capabilities,
    )

    assert not result.ready
    assert result.commissioning_valid
    assert result.unavailable_capabilities == frozenset(
        {Capability.SAFETY_POWER_CONTROL}
    )


def test_missing_audit_is_uncommissioned_without_load_error(tmp_path):
    result = evaluate_startup_readiness(
        audit_path=tmp_path / "missing.json",
        configuration_fingerprint="config-a",
        capability_statuses=available_capabilities(),
    )

    assert not result.ready
    assert not result.commissioning_valid
    assert result.audit_error is None


def test_corrupt_audit_fails_closed_and_reports_error(tmp_path):
    path = tmp_path / "commissioning.json"
    path.write_text("{broken")

    result = evaluate_startup_readiness(
        audit_path=path,
        configuration_fingerprint="config-a",
        capability_statuses=available_capabilities(),
    )

    assert not result.ready
    assert not result.commissioning_valid
    assert result.audit_error is not None


def test_incomplete_saved_commissioning_loads_but_is_not_ready(tmp_path):
    path = tmp_path / "commissioning.json"

    incomplete = CommissioningAuditRecord(
        configuration_fingerprint="config-a",
        entries=(
            CommissioningAuditEntry(
                check=CommissioningCheck.ASIAIR_MONITORING,
                result=CommissioningResult.VERIFIED,
                observed_at=NOW,
                summary="ASIAIR monitoring verified",
                observations={},
            ),
        ),
    )

    save_commissioning_audit(path, incomplete)

    result = evaluate_startup_readiness(
        audit_path=path,
        configuration_fingerprint="config-a",
        capability_statuses=available_capabilities(),
    )

    assert not result.ready
    assert not result.commissioning_valid
    assert result.audit_error is None
    assert (
        result.commissioning.result_for(
            CommissioningCheck.ASIAIR_MONITORING
        )
        is CommissioningResult.VERIFIED
    )
    assert (
        result.commissioning.result_for(
            CommissioningCheck.PROTECTION_LOGIC
        )
        is CommissioningResult.NOT_TESTED
    )
