"""Guardian one-click starter.

    .venv/bin/python guardian_v1_launcher.py install     puts "Start Guardian.command" on your Desktop
    .venv/bin/python guardian_v1_launcher.py start       does the next sensible thing (what the icon runs)
    .venv/bin/python guardian_v1_launcher.py where       shows what it would do, without doing it
"""
import argparse
import sys
from pathlib import Path

from modules import guardian_v1_launcher as launcher


def main(argv=None, out=print):
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["install", "start", "where"])
    parser.add_argument("--desktop", default=None, help="where to put the icon (default: your Desktop)")
    args = parser.parse_args(argv)
    folder = Path(__file__).resolve().parent
    if args.command == "install":
        return 0 if launcher.install(folder, args.desktop, out=out) else 2
    if args.command == "where":
        state = launcher.inspect(folder)
        out(f"Next action: {launcher.decide(state)}")
        out(f"  Python environment: {state.has_venv}   configuration: {state.has_config}   "
            f"setup file waiting: {state.candidate or 'no'}   app built: {state.has_app}")
        return 0
    launcher.start(folder, out=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
