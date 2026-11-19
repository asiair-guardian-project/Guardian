"""Guardian 1.0 commissioning workflow."""

from modules.commissioning_audit import (
    CommissioningAuditEntry,
    CommissioningAuditRecord,
)

from modules.commissioning import (
    CommissioningCheck,
    CommissioningEvidence,
    CommissioningResult,
    CommissioningStatus,
    evaluate_commissioning_evidence,
)


class CommissioningSession:
    """Collect explicit commissioning evidence for one configuration."""

    def __init__(self, configuration_fingerprint: str):
        if not configuration_fingerprint:
            raise ValueError("configuration_fingerprint must not be empty")

        self._configuration_fingerprint = configuration_fingerprint
        self._results: dict[
            CommissioningCheck,
            CommissioningResult,
        ] = {}
        self._evidence: dict[
            CommissioningCheck,
            CommissioningEvidence,
        ] = {}

    @property
    def configuration_fingerprint(self) -> str:
        return self._configuration_fingerprint

    def record_evidence(
        self,
        evidence: CommissioningEvidence,
    ) -> None:
        """Evaluate and retain auditable commissioning evidence."""

        self._evidence[evidence.check] = evidence
        self._results[evidence.check] = evaluate_commissioning_evidence(
            evidence
        )

    def evidence_for(
        self,
        check: CommissioningCheck,
    ) -> CommissioningEvidence | None:
        """Return retained evidence for one commissioning check."""

        return self._evidence.get(check)

    def audit_record(self) -> CommissioningAuditRecord:
        """Return the evidence retained for this commissioning session."""

        entries = tuple(
            CommissioningAuditEntry(
                check=check,
                result=self._results[check],
                observed_at=evidence.observed_at,
                summary=evidence.summary,
                observations=dict(evidence.observations),
            )
            for check, evidence in self._evidence.items()
        )

        return CommissioningAuditRecord(
            configuration_fingerprint=self._configuration_fingerprint,
            entries=entries,
        )

    def status(self) -> CommissioningStatus:
        """Return an immutable snapshot of current commissioning evidence."""

        return CommissioningStatus(
            results=dict(self._results),
            configuration_fingerprint=self._configuration_fingerprint,
        )
