"""Write an operator-attested, non-authorizing Phase A hardware test record."""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FINGERPRINT = '911dd714f44fbede7c72ce442d20b6345aec3061216a460f562e9dc0f546701f'


def build_record(recorded_at):
    return {
        'schema': 'guardian-physical-acceptance-observation-v1',
        'recorded_at_utc': recorded_at,
        'test_window_utc_approx': '2026-10-29T17:12:00Z/2026-10-29T17:15:00Z',
        'timestamp_note': 'Approximate from operator conversation; original CLI output was not timestamped.',
        'configuration_fingerprint_sha256': FINGERPRINT,
        'phase': 'A_PHYSICAL_POWER_SHUTDOWN',
        'source': 'Operator-provided terminal output and Tapo/remote-session observations; not an independently archived machine log',
        'initial_conditions': {
            'roof_closed': 'operator_confirmed',
            'imaging_stopped': 'operator_confirmed',
            'mount_stationary_and_parked': 'operator_confirmed',
            'outlets_1_2_3_4_on': 'kasa_get_outlets_output_provided',
        },
        'controller': 'modules.kasa_controller.KasaController.power_off_emergency_targets',
        'targets': [
            {'outlet': 2, 'alias': 'ASIAIR', 'command_sent': True, 'is_on': False, 'verified_off': True},
            {'outlet': 3, 'alias': 'Wave 150i', 'actual_device': 'AM5 loaner mount', 'command_sent': True, 'is_on': False, 'verified_off': True},
            {'outlet': 4, 'alias': 'Pegasus', 'command_sent': True, 'is_on': False, 'verified_off': True},
        ],
        'operator_observations': {
            'tapo_all_three_targets_off': True,
            'texas_mac_remote_connection_remained_available': True,
            'outlet_1_post_shutdown_direct_kasa_read': 'not_performed',
        },
        'phase_a_observed_result': 'PASS',
        'integrated_guardian_emergency_pathway': 'NOT_TESTED',
        'commissioning_checks': {
            'ASIAIR_SAFETY_POWER': 'PENDING_REVIEW',
            'MOUNT_SAFETY_POWER': 'PENDING_REVIEW',
            'ACCESSORIES_SAFETY_POWER': 'PENDING_REVIEW',
            'GUARDIAN_SURVIVAL': 'PENDING_REVIEW',
        },
        'commissioned': False,
        'hardware_authorized': False,
        'note': 'Reconstructed record from observed output. Does not call commissioning persistence or change runtime state.',
    }


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as f:
            temp = Path(f.name)
            json.dump(record, f, indent=2, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite existing record: {path}')
        os.replace(temp, path)
        temp = None
    finally:
        if temp and temp.exists():
            temp.unlink()
    if json.loads(path.read_text(encoding='utf-8')) != record:
        raise RuntimeError('Record readback mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('commissioning_reports/physical_phase_a_20261029.json'))
    args = parser.parse_args()
    record = build_record(datetime.now(timezone.utc).isoformat())
    save(args.output, record)
    print('REPORT_PATH=' + str(args.output.resolve()))
    print('PHASE_A_OBSERVED_RESULT=PASS')
    print('INTEGRATED_EMERGENCY=NOT_TESTED')
    print('COMMISSIONING_STATUS=NOT_AUTHORIZED')

if __name__ == '__main__':
    main()
