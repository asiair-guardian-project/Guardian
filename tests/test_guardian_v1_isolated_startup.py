import json
import plistlib
from pathlib import Path
from guardian_v1_isolated_startup import run_isolated
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore


def test_isolated_startup_never_changes_production_recovery(tmp_path):
    production = tmp_path / 'production.json'
    production.write_text(json.dumps({
        'schema_version': 2, 'active_incident': None, 'abort_acknowledged': False,
        'incident_history': [], 'session_state': 'DISARMED',
        'shutdown_clean': True, 'recovery_required': False,
    }))
    before = production.read_bytes()
    plist = tmp_path / 'agent.plist'
    argv = ['python', 'guardian_v1.py', '--continuous-monitor']
    for flag, val in [('--recovery-file', str(production)), ('--operator-socket', '/tmp/live.sock'),
                      ('--asiair-host', 'example.invalid'), ('--alpaca-host', 'example.invalid'),
                      ('--alpaca-port', '443'), ('--alpaca-device', '17')]:
        argv.extend([flag, val])
    plist.write_bytes(plistlib.dumps({'ProgramArguments': argv, 'RunAtLoad': True, 'KeepAlive': False}))
    seen = []
    class Observation:
        _commissioning = object()
        _configuration_fingerprint = 'uncommissioned'
    def fake_composer(**kwargs):
        seen.append(kwargs)
        return Observation()
    report = run_isolated(launchagent=plist, kasa_host='192.168.1.30', composer=fake_composer)
    assert report['armed'] is False
    assert report['hardware_execution'] == 'DISABLED'
    assert report['owner_socket'] == 'CONSTRUCTED_NOT_STARTED'
    assert seen[0]['kasa_host'] == '192.168.1.30'
    assert production.read_bytes() == before
    assert not (tmp_path / 'live.sock').exists()
