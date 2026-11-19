#!/usr/bin/env python3
"""Create the Guardian 1.0 monitor launchd file (WATCHING ONLY) from your installation config.

    .venv/bin/python guardian_v1_install_monitor.py --config config/config.yaml            # shows the file, writes nothing
    .venv/bin/python guardian_v1_install_monitor.py --config config/config.yaml --write    # writes it (never overwrites)

Never loads the job, never arms Guardian, never contacts a device, never switches power.
"""
import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from modules.guardian_v1_monitor_job import (  # noqa: E402
    ALERT_LEVELS, MonitorJobError, build_plist, default_plist_path, default_support_dir, next_steps, write_plist)
from modules.guardian_v1_setup_config import read_installation  # noqa: E402


def main(argv=None, out=print) -> int:
    parser = argparse.ArgumentParser(description="Create the Guardian 1.0 watching-only monitor launchd file")
    parser.add_argument("--config", required=True, help="the installation config (e.g. config/config.yaml)")
    parser.add_argument("--write", action="store_true", help="write the file (default: show it only)")
    parser.add_argument("--plist", default=None, help="where to write (default ~/Library/LaunchAgents/...)")
    parser.add_argument("--support-dir", default=None, help="default ~/Library/Application Support/GuardianV1")
    parser.add_argument("--python", default=None, help="default: the python running this command")
    parser.add_argument("--alert-level", default="off", choices=ALERT_LEVELS)
    args = parser.parse_args(argv)
    try:
        config = Path(args.config).expanduser().resolve()
        installation = read_installation(config)
        plist = build_plist(installation, project_dir=PROJECT, python=args.python or sys.executable,
                            config_path=config, support_dir=args.support_dir, alert_level=args.alert_level)
        target = Path(args.plist).expanduser() if args.plist else default_plist_path()
        if not args.write:
            out("DRY RUN (nothing written). The monitor job would be:")
            out("  " + " ".join(f'"{a}"' if " " in a else a for a in plist["ProgramArguments"]))
            out(f"  to be written to {target}; logs and recovery files in {args.support_dir or default_support_dir()}")
            out("Add --write to create it. It can not cut power.")
            return 0
        written = write_plist(plist, target, args.support_dir)
    except (MonitorJobError, OSError, ValueError) as error:
        out(f"REFUSED: {error}")
        return 1
    for line in next_steps(written):
        out(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
