"""Guardian 1.0 commissioning evidence coordinator."""

from collections.abc import Iterable

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
    CommissioningStatus,
)
from modules.commissioning_service import CommissioningSession


def assemble_commissioning_status(
    *,
    configuration_fingerprint: str,
    evidence: Iterable[CommissioningEvidence],
) -> CommissioningStatus:
    """Assemble commissioning evidence for one safety configuration."""

    session = CommissioningSession(configuration_fingerprint)
    seen: set[CommissioningCheck] = set()

    for item in evidence:
        if item.check in seen:
            raise ValueError(
                f"duplicate commissioning evidence for {item.check.name}"
            )

        seen.add(item.check)
        session.record_evidence(item)

    return session.status()
