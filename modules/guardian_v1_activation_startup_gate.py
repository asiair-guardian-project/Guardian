"""Fail-closed startup gate for interrupted Phase C activation.

A verified on-disk replacement is not evidence that the running monitor or
commissioning identity was reconciled. Only a separate, audited maintenance
procedure may archive the journal after restart verification.
"""
from pathlib import Path
from modules.guardian_v1_activation_journal import read_journal


class ActivationStartupBlocked(RuntimeError):
    pass


def assert_no_pending_activation(installation_path):
    """Refuse monitoring when any activation journal exists, even VERIFIED.

    Journal contents may be corrupt or partially written; do not attempt to
    repair or delete it from the normal monitor startup path.
    """
    active = Path(installation_path).expanduser().absolute()
    journal = active.with_name('config.guardian-activation-journal.json')
    if journal.is_symlink():
        raise ActivationStartupBlocked('Activation journal symlink: maintenance required')
    if journal.exists():
        try:
            read_journal(journal)
        except Exception as exc:
            raise ActivationStartupBlocked('Invalid activation journal: maintenance required') from exc
        raise ActivationStartupBlocked('Activation journal pending: maintenance reconciliation required')
    return True
