"""Read-only evidence reconciliation; never modifies commissioning authorization."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

CHECKS = (
    'ASIAIR_MONITORING', 'OBSERVATORY_SAFETY', 'ASIAIR_SAFETY_POWER',
    'MOUNT_SAFETY_POWER', 'GUARDIAN_SURVIVAL', 'SIMULTANEOUS_PATHS',
    'PROTECTION_LOGIC', 'ACCESSORIES_SAFETY_POWER',
)
POWER_CHECKS = ('ASIAIR_SAFETY_POWER', 'MOUNT_SAFETY_POWER', 'ACCESSORIES_SAFETY_POWER')

def reconcile(root: Path, fingerprint: str):
    root = Path(root)
    phase_b = root / 'phase_b_live' / 'phase_b_live_20261029_01.outcome.json'
    if not phase_b.is_file():
        raise FileNotFoundError(f'Live outcome journal not found: {phase_b}')
    raw = phase_b.read_bytes()
    journal = json.loads(raw)
    # The durable authorization writer wraps the actual runner result in
    # `details`; fingerprint and bridge evidence are nested there.
    if journal.get('event') != 'PHASE_B_TEST_OUTCOME':
        raise ValueError('Unexpected Phase B outcome journal type')
    if journal.get('commissioning_status') != 'NOT_AUTHORIZED':
        raise ValueError('Unexpected live journal commissioning status')
    details = journal.get('details')
    if not isinstance(details, dict):
        raise ValueError('Live outcome journal has no details')
    if details.get('configuration_fingerprint') != fingerprint:
        raise ValueError('Live journal configuration fingerprint mismatch')
    if details.get('commissioning_status') != 'NOT_AUTHORIZED':
        raise ValueError('Unexpected live details commissioning status')
    if details.get('test_id') != journal.get('test_id'):
        raise ValueError('Outcome test ID mismatch')
    if details.get('status') != journal.get('status'):
        raise ValueError('Outcome status mismatch')
    status = details.get('status')
    if status != 'PASS' or details.get('independent_outlet_verification') is not True:
        raise ValueError('Live journal does not establish successful independent shutdown verification')
    marker_path = phase_b.with_name(phase_b.name.replace('.outcome.json', '.consumed.json'))
    if not marker_path.is_file():
        raise ValueError('Missing durable authorization-consumption record')
    marker = json.loads(marker_path.read_bytes())
    if marker.get('event') != 'PHASE_B_AUTHORIZATION_CONSUMED' or marker.get('test_id') != journal.get('test_id'):
        raise ValueError('Authorization-consumption record mismatch')
    requested = marker.get('requested') or {}
    approved = marker.get('approved_scope') or {}
    expected_roles = ['ACCESSORIES', 'ASIAIR', 'MOUNT']
    if (requested != approved or requested.get('configuration_fingerprint') != fingerprint
            or requested.get('controller_id') != details.get('controller_id')
            or requested.get('roles') != expected_roles):
        raise ValueError('Durable authorization scope does not match live outcome')
    bridge = details.get('bridge') or {}
    if bridge.get('passed') is not True or sorted(bridge.get('roles') or []) != expected_roles:
        raise ValueError('Bridge result is missing or inconsistent')
    try:
        results = dict(bridge.get('results') or [])
    except (TypeError, ValueError) as exc:
        raise ValueError('Malformed bridge role results') from exc
    if len(bridge.get('results') or []) != len(results):
        raise ValueError('Duplicate bridge role results')
    for role in expected_roles:
        if results.get(role) != 'VERIFIED_OFF':
            raise ValueError(f'Live bridge lacks VERIFIED_OFF for {role}')
    if len(results) != len(expected_roles):
        raise ValueError('Unexpected bridge role results')
    checks = {}
    for check in CHECKS:
        if check in POWER_CHECKS:
            assessment = 'PHYSICAL_EXECUTION_EVIDENCE_PRESENT_REVIEW_REQUIRED'
            note = 'Phase B live journal reports verified shutdown; formal commissioning evidence acceptance remains pending.'
        elif check == 'GUARDIAN_SURVIVAL':
            assessment = 'SUPPORTING_EVIDENCE_REVIEW_REQUIRED'
            note = 'Protected host observed ON after test; broader Guardian survival acceptance remains pending.'
        else:
            assessment = 'OTHER_EVIDENCE_REVIEW_REQUIRED'
            note = 'Existing automated or observational evidence must be evaluated separately; not established by this physical power test.'
        checks[check] = {'assessment': assessment, 'note': note}
    return {
        'schema_version': 1,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'configuration_fingerprint': fingerprint,
        'source': str(phase_b),
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'authorization_source': str(marker_path),
        'authorization_sha256': hashlib.sha256(marker_path.read_bytes()).hexdigest(),
        'physical_test_status': status,
        'physical_roof_event': details.get('physical_roof_event', 'UNKNOWN'),
        'commissioning_status': 'NOT_AUTHORIZED',
        'changes_production_audit': False,
        'checks': checks,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--reports-dir', default='commissioning_reports')
    p.add_argument('--fingerprint', required=True)
    args = p.parse_args()
    result = reconcile(Path(args.reports_dir), args.fingerprint)
    print(json.dumps(result, indent=2))
    print('RECONCILIATION=COMPLETE; COMMISSIONING=NOT_AUTHORIZED; AUDIT_UNCHANGED')

if __name__ == '__main__':
    main()
