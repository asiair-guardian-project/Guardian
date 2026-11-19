"""Stage B helper: status / switch / rollback. Dry run unless --apply is given."""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from modules.guardian_v1_stage_b import (  # noqa: E402
    StageBError, real_environment, rollback, supervisor_report, switch)
from modules.guardian_v1_start_guard import DEFAULT_SOCKET  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Guardian Stage B helper")
    parser.add_argument("action", choices=["status", "switch", "rollback"])
    parser.add_argument("--apply", action="store_true", help="really do it (default is a dry run)")
    parser.add_argument("--operator-socket", default=str(DEFAULT_SOCKET))
    parser.add_argument("--launch-agents", default=None, help="folder holding the launchd files (default ~/Library/LaunchAgents)")
    args = parser.parse_args(argv)

    env = real_environment(PROJECT, args.operator_socket, args.launch_agents)

    try:
        if args.action == "status":
            lines, protected_by = supervisor_report(env)
            for line in lines:
                print(line)
            print(f"PROTECTED_BY: {protected_by}")
            return 0
        if args.action == "switch":
            return switch(env, args.apply)
        return rollback(env, args.apply)
    except StageBError as exc:
        print(f"REFUSED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
