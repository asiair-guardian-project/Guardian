"""Non-authorizing evidence reconciliation for Guardian 1.0.

This tool never writes a CommissioningStatus, recovery file, or hardware state.
"""
import json
from modules.commissioning import CommissioningCheck, CommissioningResult, CommissioningStatus

# Prior observations are leads for audit, NOT independently verified records.
CANDIDATES = {
    'ASIAIR_MONITORING': ('Prior live/shadow monitoring; latest ASIAIR observation was NOT_ESTABLISHED with outlet off', 'Recheck online state with ASIAIR powered on'),
    'OBSERVATORY_SAFETY': ('Prior Alpaca roof CLOSED observations and shadow monitoring', 'Confirm roof freshness, errors, and state transitions'),
    'ASIAIR_SAFETY_POWER': ('Previously observed HS300 outlet 2 OFF and VERIFIED_OFF', 'Attach dated test output and outlet alias verification'),
    'MOUNT_SAFETY_POWER': ('Previously observed HS300 outlet 3 OFF and VERIFIED_OFF', 'Confirm actual installed mount and matching outlet alias'),
    'GUARDIAN_SURVIVAL': ('Mac mini outlet 1 protected in Kasa topology', 'Verify Guardian/network remain running after all target outlets switch off'),
    'SIMULTANEOUS_PATHS': ('Simulation tests passed', 'Confirm simultaneous triggers, ordering and durable results against required acceptance criteria'),
    'PROTECTION_LOGIC': ('Simulated emergency and ARM/ABORT/recovery tests passed', 'Review evidence for persistent ABORT and no automatic rearm'),
    'ACCESSORIES_SAFETY_POWER': ('Previously observed HS300 outlet 4 OFF and VERIFIED_OFF', 'Attach dated test output and alias verification'),
}

def report(fingerprint):
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
        raise ValueError('Expected lowercase SHA-256 fingerprint')
    checks = {}
    for check in CommissioningCheck:
        prior, missing = CANDIDATES[check.name]
        checks[check.name] = {
            'commissioning_result': 'NOT_TESTED',
            'prior_evidence_to_reconcile': prior,
            'required_next_evidence': missing,
        }
    status = CommissioningStatus(results={check: CommissioningResult.NOT_TESTED for check in CommissioningCheck}, configuration_fingerprint=fingerprint)
    assert not status.valid_for_configuration(fingerprint)
    return {'fingerprint': fingerprint, 'checks': checks,
            'verified_count': 0, 'pending_count': len(checks),
            'hardware_authorized': False,
            'note': 'This is a reconciliation worksheet, not a commissioning certificate.'}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--fingerprint', required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.fingerprint), indent=2))
