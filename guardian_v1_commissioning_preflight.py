"""Read-only Guardian 1.0 commissioning preflight.

Does not create a runtime, open a socket, contact hardware, modify recovery,
or change the running LaunchAgent.
"""
import argparse
import json
import plistlib
from pathlib import Path

from modules.guardian_v1_recovery_store import validate_recovery_state

REQUIRED = ("--continuous-monitor", "--recovery-file", "--operator-socket",
            "--asiair-host", "--alpaca-host", "--alpaca-port", "--alpaca-device")


def inspect_launchagent(plist_path):
    with open(plist_path, "rb") as stream:
        agent = plistlib.load(stream)
    argv = agent.get("ProgramArguments", [])
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise ValueError("Invalid LaunchAgent arguments")
    if not all(flag in argv for flag in REQUIRED):
        raise ValueError("LaunchAgent is missing required monitor arguments")
    args = {flag: argv[argv.index(flag) + 1] for flag in REQUIRED if flag != "--continuous-monitor"}
    if any(argv.count(flag) != 1 for flag in REQUIRED):
        raise ValueError("Duplicate or missing LaunchAgent option")
    if not agent.get("RunAtLoad") or agent.get("KeepAlive") is not False:
        raise ValueError("Unexpected LaunchAgent lifecycle configuration")
    return args


def preflight(plist_path):
    args = inspect_launchagent(plist_path)
    recovery = Path(args["--recovery-file"])
    state = validate_recovery_state(json.loads(recovery.read_text(encoding="utf-8")))
    from modules.guardian_v1_application import GuardianV1Application
    from modules.guardian_types import Capability
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
    app = GuardianV1Application(
        configured_capabilities={Capability.ASIAIR_MONITORING,
                                 Capability.OBSERVATORY_SAFETY_MONITORING,
                                 Capability.SAFETY_POWER_CONTROL,
                                 Capability.SAFETY_POWER_STATE_VERIFICATION},
        recovery_store=GuardianV1RecoveryStore(recovery),
    )
    if app.mode.hardware_execution_enabled:
        raise RuntimeError("Hardware mode unexpectedly enabled")
    return {
        "launchagent": str(plist_path),
        "asiair_host": args["--asiair-host"],
        "alpaca_host": args["--alpaca-host"],
        "alpaca_port": args["--alpaca-port"],
        "alpaca_device": args["--alpaca-device"],
        "recovery_file": str(recovery),
        "recovery_valid": True,
        "recovery_blocked": bool(app.supervisor.recovery_blocked or app.supervisor.incident is not None),
        "session": app.supervisor.session_state.name,
        "socket_path": args["--operator-socket"],
        "hardware_execution": "DISABLED",
        "new_runtime_started": False,
        "outlet_commands": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launchagent", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(preflight(arguments.launchagent), indent=2))


if __name__ == "__main__":
    main()
