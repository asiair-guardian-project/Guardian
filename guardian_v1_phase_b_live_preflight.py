"""Read-only Phase B live-test readiness and durable preflight evidence.

No live shutdown capability; this is deliberately a pre-execution gate.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

from modules.kasa_controller import KasaController

EXPECTED = {1: ('Mac Mini', True, True), 2: ('ASIAIR', False, False),
            3: ('Wave 150i', False, False), 4: ('Pegasus', False, False)}


def evaluate(process_text, outlets):
    active = [line.strip() for line in process_text.splitlines()
              if ('guardian_v1.py' in line or 'guardian.py' in line)
              and 'grep' not in line]
    by_number = {int(o['number']): o for o in outlets}
    checks = {'no_active_guardian_process': not active}
    for number, (alias, on, protected) in EXPECTED.items():
        item = by_number.get(number)
        checks[f'outlet_{number}_identity_state'] = bool(
            item and item['name'] == alias and bool(item['is_on']) == on
            and bool(item['protected']) == protected)
    return checks, active


def save_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f'refusing to overwrite evidence: {path}')
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.phase_b_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        assert json.loads(path.read_text()) == data
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kasa-host', default='192.168.1.30')
    parser.add_argument('--fingerprint', required=True)
    args = parser.parse_args()
    process = subprocess.run(['ps', '-axo', 'pid,ppid,command'],
                             capture_output=True, text=True, check=True).stdout
    outlets = asyncio.run(KasaController(args.kasa_host).get_outlets())
    checks, active = evaluate(process, outlets)
    now = datetime.now(timezone.utc)
    report = {'timestamp_utc': now.isoformat(), 'phase': 'B_LIVE_PREFLIGHT',
              'configuration_fingerprint': args.fingerprint,
              'checks': checks, 'active_guardian_processes': active,
              'outlets': [{k: o[k] for k in ('number', 'name', 'is_on', 'protected')}
                          for o in outlets],
              'result': 'PASS' if all(checks.values()) else 'BLOCKED',
              'hardware_commands': 0, 'live_execution': 'NOT_PERFORMED',
              'commissioning_status': 'NOT_AUTHORIZED',
              'note': 'Roof and mount conditions require independent operator confirmation; this script does not verify them.'}
    path = Path('commissioning_reports') / f'phase_b_live_preflight_{now.strftime("%Y%m%dT%H%M%S%fZ")}.json'
    save_atomic(path, report)
    print(f'REPORT_PATH={path.resolve()}')
    for key, value in checks.items():
        print(f'{key}={"PASS" if value else "FAIL"}')
    print(f'PREFLIGHT={report["result"]}; HARDWARE_COMMANDS=0; LIVE_EXECUTION=NOT_PERFORMED')
    if report['result'] != 'PASS':
        raise SystemExit(2)

if __name__ == '__main__':
    main()
