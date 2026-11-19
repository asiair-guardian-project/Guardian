"""TEST-ONLY owner process for the Guardian operator window.

Never runs observation cycles or connects to equipment. Do not use as a
production Guardian service or point at a live recovery-state file.
"""
import argparse
import os
from pathlib import Path
import signal
import sys

from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_socket import GuardianOperatorSocket
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    fixture = Path(args.fixture).resolve()
    if "/tests/fixtures/" not in str(fixture):
        parser.error("Demo accepts only files under tests/fixtures/")
    app = GuardianV1Application(configured_capabilities=set(), recovery_store=GuardianV1RecoveryStore(fixture))
    if app.supervisor.recovery_blocked and app.supervisor.incident is None:
        print("Demo recovery file missing/invalid; ARM remains blocked", flush=True)
    service = GuardianOperatorSocket(app, args.socket)
    service.start()
    print("DEMO ONLY: operator socket ready. No Guardian runtime or hardware started.", flush=True)
    try:
        while True:
            service.serve_once()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()

if __name__ == "__main__":
    main()
