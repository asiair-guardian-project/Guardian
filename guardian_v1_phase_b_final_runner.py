"""Isolated Phase B hardware acceptance. NEVER arms Guardian or edits production config.

Use --plan for a zero-hardware readiness plan. --execute requires explicit,
separately obtained operator approval and live preflight; do not run unattended.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

from modules.guardian_types import SafetyPowerRole
from modules.guardian_v1_commissioning_test_authority import CommissioningTestScope
from modules.guardian_v1_phase_b_durable_authority import DurableTestAuthorization
from modules.guardian_v1_phase_b_bridge import run_isolated_shutdown
from modules.guardian_v1_starfront_kasa import CONTROLLER_ID, compose_starfront_kasa
from modules.kasa_controller import KasaController

HOST = '192.168.1.30'
ROLES = frozenset({SafetyPowerRole.ASIAIR, SafetyPowerRole.MOUNT, SafetyPowerRole.ACCESSORIES})
EXPECTED = {1: ('Mac Mini', True), 2: ('ASIAIR', True), 3: ('Wave 150i', True), 4: ('Pegasus', True)}
APPROVAL = 'I AUTHORIZE ONE PHASE B SHUTDOWN OF OUTLETS 2 3 4'


def process_check():
    output = subprocess.run(['ps', '-axo', 'pid,ppid,command'], check=True,
                            capture_output=True, text=True).stdout
    return not any(('guardian_v1.py' in line or 'guardian.py' in line) and
                   'grep' not in line for line in output.splitlines())


def check_outlets(outlets, expected):
    by_number = {int(o['number']): o for o in outlets}
    return all((o := by_number.get(n)) is not None and o['name'] == alias and
               bool(o['is_on']) == on and bool(o['protected']) == (n == 1)
               for n, (alias, on) in expected.items())


def read_outlets():
    return asyncio.run(KasaController(HOST).get_outlets())


def run_live(*, fingerprint, test_id, approval, roof_closed, mount_stationary, imaging_stopped):
    # No physical switching before these checks succeed.
    if approval != APPROVAL or not all((roof_closed, mount_stationary, imaging_stopped)):
        raise RuntimeError('explicit operator approval and all physical safety confirmations required')
    if not process_check():
        raise RuntimeError('Guardian process detected; live test blocked')
    before = read_outlets()
    if not check_outlets(before, EXPECTED):
        raise RuntimeError('HS300 identity, protected host, or energized target preflight failed')
    scope = CommissioningTestScope(
        configuration_fingerprint=fingerprint, controller_id=CONTROLLER_ID,
        roles=frozenset(role.name for role in ROLES))
    auth = DurableTestAuthorization(journal_dir=Path('commissioning_reports/phase_b_live'),
                                    test_id=test_id, scope=scope)
    outcome = {'test_id': test_id, 'before': before, 'configuration_fingerprint': fingerprint,
               'controller_id': CONTROLLER_ID, 'commissioning_status': 'NOT_AUTHORIZED',
               'physical_roof_event': 'NOT_TESTED'}
    status = 'UNKNOWN'
    try:
        # Uses Guardian 1.0 generic SafetyPowerManager path; not the Phase A batch method.
        wiring = compose_starfront_kasa(host=HOST)
        result = run_isolated_shutdown(authorization=auth, fingerprint=fingerprint,
                                       controller_id=CONTROLLER_ID, roles=ROLES,
                                       execute_safety_power=wiring.execute_safety_power)
        outcome['bridge'] = {'passed': result.passed, 'results': list(result.results),
                             'roles': list(result.roles)}
        status = 'PASS' if result.passed else 'FAIL'
    except BaseException as exc:
        outcome['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
        status = 'EXCEPTION'
    finally:
        # Independently read outlet states even after partial failure.
        try:
            after = read_outlets()
            outcome['after'] = after
            expected_after = {1: ('Mac Mini', True), 2: ('ASIAIR', False),
                              3: ('Wave 150i', False), 4: ('Pegasus', False)}
            verified = check_outlets(after, expected_after)
            outcome['independent_outlet_verification'] = verified
            if not verified:
                status = 'FAIL'
        except BaseException as exc:
            outcome['postflight_error'] = f'{type(exc).__name__}: {exc}'
            status = 'UNKNOWN'
        outcome['status'] = status
        outcome['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
        # Only a consumed test can have an outcome; preserve unresolved evidence on errors.
        if auth.marker.exists():
            auth.record_outcome(status=status, details=outcome)
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--test-id')
    parser.add_argument('--approval')
    parser.add_argument('--roof-closed', action='store_true')
    parser.add_argument('--mount-stationary', action='store_true')
    parser.add_argument('--imaging-stopped', action='store_true')
    args = parser.parse_args()
    if args.plan and not args.execute:
        print('MODE=PLAN_ONLY; HARDWARE_COMMANDS=0; PRODUCTION_GUARDIAN=UNCHANGED')
        print('REQUIRED: exclusive process ownership, roof closed, mount stationary, imaging stopped')
        print('REQUIRED: outlets 1-4 identities, outlet 1 ON protected, outlets 2-4 ON')
        print('LIVE_EXECUTION=NOT_PERFORMED; COMMISSIONING=NOT_AUTHORIZED')
        return
    if not args.execute:
        parser.error('specify --plan or --execute')
    if not args.test_id:
        parser.error('--test-id required for live execution')
    result = run_live(fingerprint=args.fingerprint, test_id=args.test_id,
                      approval=args.approval, roof_closed=args.roof_closed,
                      mount_stationary=args.mount_stationary, imaging_stopped=args.imaging_stopped)
    print('PHASE_B_RESULT=' + result['status'])
    print('JOURNAL=commissioning_reports/phase_b_live/' + args.test_id + '.outcome.json')
    print('COMMISSIONING_STATUS=NOT_AUTHORIZED')
    if result['status'] != 'PASS':
        raise SystemExit(2)

if __name__ == '__main__':
    main()
