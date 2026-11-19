#!/usr/bin/env python3
"""Guardian 1.0 read-only-to-hardware macOS recovery acceptance test.

Run from ObservatorySupervisor root: python guardian_v1_macos_acceptance.py
Uses only temporary files; no observatory network, power, or mount adapters.
"""
import json
import os
import tempfile
from pathlib import Path

from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore, RecoveryStateError
from modules.guardian_types import ProtectionTrigger, SafetyPowerResult, SessionState
from modules.protection_coordinator import initiate_protection
from modules.protection_planner import build_protection_plan
from modules.runtime_supervisor import RuntimeSupervisor


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print('PASS:', message)


def main():
    with tempfile.TemporaryDirectory(prefix='guardian-v1-macos-acceptance-') as directory:
        root = Path(directory)
        store = GuardianV1RecoveryStore(root / 'recovery.json')
        store.write(RuntimeSupervisor().export_recovery_state())
        app = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
        check(app.mode.monitor_only, 'Hardware execution starts disabled')
        check(not app.supervisor.recovery_blocked, 'Clean disarmed startup')
        check(store.read()['session_state'] == SessionState.DISARMED.name,
              'Atomic JSON recovery write/read')
        check(not list(root.glob('*.tmp')), 'No temporary recovery files left behind')

        incident = initiate_protection(
            triggers={ProtectionTrigger.ROOF_CLOSED},
            execute_action=lambda action: SafetyPowerResult.FAILED,
        )
        app.supervisor._incident = incident  # Simulated incident; no hardware calls
        app.supervisor._session_state = SessionState.ABORTED
        store.write(app.supervisor.export_recovery_state())
        restarted = GuardianV1Application(configured_capabilities=set(), recovery_store=store)
        check(restarted.supervisor.incident is not None and restarted.supervisor.recovery_blocked,
              'Simulated ABORT persists across process restart')
        check(restarted.acknowledge_abort(), 'Operator acknowledgment persisted')
        check(not restarted.authorize_new_session(), 'Unresolved incident blocks new session')
        # Update the incident via pure in-memory fake results and persist snapshot.
        restarted.supervisor.incident.retry_unresolved(
            lambda action: SafetyPowerResult.VERIFIED_OFF
        )
        store.write(restarted.supervisor.export_recovery_state())
        check(not restarted.authorize_new_session(),
              'Restarted incident requires fresh independent verification')
        for action in build_protection_plan():
            restarted.supervisor.record_fresh_power_verification(
                action, SafetyPowerResult.VERIFIED_OFF
            )
        check(restarted.authorize_new_session(),
              'Explicit acknowledgment and fresh verification permit DISARMED release')
        check(store.read()['active_incident'] is None, 'Incident release persisted')
        check(len(store.read()['incident_history']) == 1, 'Incident history retained')
        check(not GuardianV1Application(
            configured_capabilities=set(), recovery_store=store
        ).supervisor.recovery_blocked, 'Disarmed restart does not falsely block')

        broken = root / 'corrupt.json'
        broken.write_text('{not json', encoding='utf-8')
        blocked = GuardianV1Application(
            configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(broken)
        )
        check(blocked.supervisor.recovery_blocked and broken.read_text() == '{not json',
              'Corrupt recovery state blocks ARM and is not overwritten')
        missing = GuardianV1Application(
            configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(root / 'missing.json')
        )
        check(missing.supervisor.recovery_blocked, 'Missing recovery state blocks ARM')
        print('\nALL MACOS RECOVERY ACCEPTANCE CHECKS PASSED')


if __name__ == '__main__':
    main()
