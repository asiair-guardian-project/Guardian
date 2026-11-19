"""Guardian 1.0 startup readiness restoration."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from modules.capability_model import (
    installation_ready,
    unavailable_required_capabilities,
)
from modules.commissioning import CommissioningStatus
from modules.commissioning_persistence import (
    CommissioningPersistenceError,
    load_commissioning_audit,
)
from modules.guardian_types import Capability, CapabilityStatus


@dataclass(frozen=True)
class StartupReadiness:
    """Diagnostic result of restoring installation readiness."""

    ready: bool
    commissioning: CommissioningStatus
    commissioning_valid: bool
    unavailable_capabilities: frozenset[Capability]
    audit_error: str | None = None


def evaluate_startup_readiness(
    *,
    audit_path: str | Path,
    configuration_fingerprint: str,
    capability_statuses: Mapping[Capability, CapabilityStatus],
) -> StartupReadiness:
    """Restore commissioning and evaluate current installation readiness."""

    path = Path(audit_path)
    audit_error = None

    if path.exists():
        try:
            commissioning = load_commissioning_audit(path).status()
        except CommissioningPersistenceError as exc:
            commissioning = CommissioningStatus(
                results={},
                configuration_fingerprint=None,
            )
            audit_error = str(exc)
    else:
        commissioning = CommissioningStatus(
            results={},
            configuration_fingerprint=None,
        )

    commissioning_valid = commissioning.valid_for_configuration(
        configuration_fingerprint
    )

    unavailable = frozenset(
        unavailable_required_capabilities(capability_statuses)
    )

    ready = installation_ready(
        commissioning,
        configuration_fingerprint,
        capability_statuses,
    )

    return StartupReadiness(
        ready=ready,
        commissioning=commissioning,
        commissioning_valid=commissioning_valid,
        unavailable_capabilities=unavailable,
        audit_error=audit_error,
    )
