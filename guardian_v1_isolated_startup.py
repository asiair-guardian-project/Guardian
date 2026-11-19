"""Opt-in isolated Starfront runtime smoke test. Never starts the operator server.

The production recovery JSON is read but NEVER opened for writing. The new
runtime receives a private copy in a temporary directory. All execution is
monitor-only and DISARMED, regardless of observed conditions.
"""
import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from guardian_v1_commissioning_preflight import inspect_launchagent
from modules.guardian_types import Capability
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
from modules.guardian_v1_gated_owner import GuardianV1GatedOwner
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore, validate_recovery_state
from modules.guardian_v1_starfront_kasa_integration import compose_starfront_kasa_integration

CAPABILITIES = {
    Capability.ASIAIR_MONITORING,
    Capability.OBSERVATORY_SAFETY_MONITORING,
    Capability.SAFETY_POWER_CONTROL,
    Capability.SAFETY_POWER_STATE_VERIFICATION,
}


def run_isolated(*, launchagent, kasa_host, run_observation=False, composer=compose_starfront_kasa_integration):
    config = inspect_launchagent(launchagent)
    production_recovery = Path(config['--recovery-file'])
    # Validate before copying; never modify the original.
    validate_recovery_state(json.loads(production_recovery.read_text(encoding='utf-8')))
    with tempfile.TemporaryDirectory(prefix='guardian-v1-isolated-') as tmp:
        tmp = Path(tmp)
        recovery_copy = tmp / 'recovery.json'
        shutil.copyfile(production_recovery, recovery_copy)
        app = GuardianV1Application(
            configured_capabilities=CAPABILITIES,
            recovery_store=GuardianV1RecoveryStore(recovery_copy),
        )
        observation = composer(
            application=app,
            asiair_host=config['--asiair-host'],
            alpaca_host=config['--alpaca-host'],
            alpaca_port=int(config['--alpaca-port']),
            alpaca_device_number=int(config['--alpaca-device']),
            kasa_host=kasa_host,
        )
        gate = GuardianV1ArmedGate(application=app, observation_runtime=observation)
        # Construct the socket owner, but do NOT call owner.run() or socket.start().
        owner = GuardianV1GatedOwner(gate=gate, socket_path=tmp / 'operator.sock')
        assert owner.gate is gate and owner.socket.gate is gate
        assert not gate.armed and not app.mode.hardware_execution_enabled
        result = {
            'composition': 'OK',
            'owner_socket': 'CONSTRUCTED_NOT_STARTED',
            'session': app.supervisor.session_state.name,
            'armed': gate.armed,
            'hardware_execution': 'DISABLED',
            'commissioning': 'UNCOMMISSIONED',
            'production_recovery_modified': False,
            'production_socket_touched': False,
            'kasa_shutdown_commands': 'PROHIBITED_BY_MODE',
        }
        if run_observation:
            cycle = gate.cycle(now=datetime.now(timezone.utc))
            result['observation'] = {
                'roof': cycle.observation.roof_state.name,
                'asiair': cycle.observation.asiair_state.name,
            }
            assert not gate.armed and not app.mode.hardware_execution_enabled
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launchagent', type=Path, required=True)
    parser.add_argument('--kasa-host', required=True)
    parser.add_argument('--observe-once', action='store_true',
                        help='Perform one monitor-only observation cycle; may contact configured devices')
    args = parser.parse_args()
    print(json.dumps(run_isolated(launchagent=args.launchagent, kasa_host=args.kasa_host,
                                  run_observation=args.observe_once), indent=2))


if __name__ == '__main__':
    main()
