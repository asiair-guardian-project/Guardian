"""Guardian 1.0 installation commissioning model."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Mapping


class CommissioningCheck(Enum):
    ASIAIR_MONITORING = auto()
    OBSERVATORY_SAFETY = auto()
    ASIAIR_SAFETY_POWER = auto()
    MOUNT_SAFETY_POWER = auto()
    GUARDIAN_SURVIVAL = auto()
    SIMULTANEOUS_PATHS = auto()
    PROTECTION_LOGIC = auto()
    ACCESSORIES_SAFETY_POWER = auto()


class CommissioningResult(Enum):
    VERIFIED = auto()
    FAILED = auto()
    NOT_TESTED = auto()


REQUIRED_COMMISSIONING_CHECKS = frozenset(CommissioningCheck)


@dataclass(frozen=True)
class CommissioningEvidence:
    """Auditable evidence produced by one commissioning procedure."""

    check: CommissioningCheck
    completed: bool
    passed: bool
    observed_at: datetime
    summary: str
    observations: Mapping[str, Any]


def evaluate_commissioning_evidence(
    evidence: CommissioningEvidence,
) -> CommissioningResult:
    """Convert observed commissioning evidence to a result."""

    if not evidence.completed:
        return CommissioningResult.FAILED

    if not evidence.passed:
        return CommissioningResult.FAILED

    return CommissioningResult.VERIFIED


@dataclass(frozen=True)
class CommissioningStatus:
    results: Mapping[CommissioningCheck, CommissioningResult]
    configuration_fingerprint: str | None = None

    def result_for(
        self,
        check: CommissioningCheck,
    ) -> CommissioningResult:
        return self.results.get(
            check,
            CommissioningResult.NOT_TESTED,
        )

    @property
    def commissioned(self) -> bool:
        return all(
            self.result_for(check) is CommissioningResult.VERIFIED
            for check in REQUIRED_COMMISSIONING_CHECKS
        )

    def valid_for_configuration(
        self,
        configuration_fingerprint: str,
    ) -> bool:
        """Return whether commissioning authorizes this configuration."""

        return (
            self.commissioned
            and self.configuration_fingerprint is not None
            and self.configuration_fingerprint == configuration_fingerprint
        )

    @property
    def unresolved_checks(self) -> frozenset[CommissioningCheck]:
        return frozenset(
            check
            for check in REQUIRED_COMMISSIONING_CHECKS
            if self.result_for(check) is not CommissioningResult.VERIFIED
        )
