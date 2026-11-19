"""Offline Phase B integration rehearsal. Never enables hardware or calls live devices."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

TESTS = (
    'tests/test_guardian_v1_full_integrated_acceptance.py',
    'tests/test_guardian_v1_commissioning_interlocks.py',
    'tests/test_guardian_v1_commissioning_transition.py',
    'tests/test_guardian_v1_overnight_recovery_acceptance.py',
)

def command_plan(root: Path, fingerprint: str):
    if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
        raise ValueError('Invalid configuration fingerprint')
    missing = [name for name in TESTS if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError('Missing acceptance modules: ' + ', '.join(missing))
    if not (root / 'guardian_v1_acceptance_reporting.py').is_file():
        raise FileNotFoundError('Existing acceptance reporter is missing')
    xml = root / 'commissioning_reports' / 'phase_b_dry_run.xml'
    test_cmd = [sys.executable, '-m', 'pytest', '-q', *TESTS, f'--junitxml={xml}']
    report_cmd = [sys.executable, 'guardian_v1_acceptance_reporting.py', '--junit', str(xml), '--fingerprint', fingerprint]
    return test_cmd, report_cmd

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--show-plan', action='store_true', help='Print commands without executing tests')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    test_cmd, report_cmd = command_plan(root, args.fingerprint)
    print('MODE=OFFLINE_SIMULATION_ONLY', flush=True)
    print('PRODUCTION_RUNTIME=UNCHANGED', flush=True)
    print('HARDWARE_COMMANDS=0', flush=True)
    print('TEST_COMMAND=' + json.dumps(test_cmd), flush=True)
    print('REPORT_COMMAND=' + json.dumps(report_cmd), flush=True)
    if args.show_plan:
        return
    (root / 'commissioning_reports').mkdir(exist_ok=True)
    result = subprocess.run(test_cmd, cwd=root, check=False)
    if result.returncode != 0:
        print('PHASE_B_DRY_RUN=FAILED; no report promoted to acceptance', file=sys.stderr)
        raise SystemExit(result.returncode)
    result = subprocess.run(report_cmd, cwd=root, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print('PHASE_B_DRY_RUN=PASSED; LIVE_INTEGRATION=NOT_TESTED; COMMISSIONING=NOT_AUTHORIZED')

if __name__ == '__main__':
    main()
