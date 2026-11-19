"""Guardian 1.0 commissioning audit record."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    CommissioningStatus,
)


@dataclass(frozen=True)
class CommissioningAuditEntry:
    """Auditable result of one commissioning check."""

    check: CommissioningCheck
    result: CommissioningResult
    observed_at: datetime
    summary: str
    observations: Mapping[str, Any]


@dataclass(frozen=True)
class CommissioningAuditRecord:
    """Evidence record for one commissioned safety configuration."""

    configuration_fingerprint: str
    entries: tuple[CommissioningAuditEntry, ...]

    def status(self) -> CommissioningStatus:
        """Reconstruct commissioning status from this audit record."""

        return CommissioningStatus(
            results={
                entry.check: entry.result
                for entry in self.entries
            },
            configuration_fingerprint=self.configuration_fingerprint,
        )

    def entry_for(
        self,
        check: CommissioningCheck,
    ) -> CommissioningAuditEntry | None:
        for entry in self.entries:
            if entry.check is check:
                return entry

        return None
