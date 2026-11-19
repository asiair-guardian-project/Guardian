"""Rehearse Guardian 1.0's abort / acknowledge / release / re-arm flow on a SIMULATED rig.

Nothing real is touched: no strip, no ASIAIR, no roof, no live recovery file, no live socket.

    .venv/bin/python guardian_v1_sim_night.py
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from modules.guardian_v1_sim_night import SimRig, build_sim_monitor, prepare_folder  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Simulated Guardian 1.0 rehearsal")
    parser.add_argument("--folder", default=None, help="a NEW empty folder (default: a fresh one under /tmp)")
    args = parser.parse_args(argv)

    folder = prepare_folder(args.folder)
    say = lambda text: print(text, flush=True)
    rig = SimRig(folder, say=say)
    runner = build_sim_monitor(folder, rig)
    socket_path = folder / "operator.sock"

    say("=== Guardian 1.0 REHEARSAL (everything here is simulated) ===")
    say(f"Folder: {folder}")
    say("")
    say("1. In ANOTHER Terminal window, open the Guardian 1.0 app pointed at this rehearsal:")
    say(f'     GUARDIAN_V1_SOCKET="{socket_path}" "$HOME/ObservatorySupervisor/Guardian 1.0.app/Contents/MacOS/GuardianDesktop"')
    say("   (it shows a purple REHEARSAL banner; the live monitor is not involved)")
    say("2. ARM it in the app. In about 10 seconds the simulated session becomes IMAGING_PERMITTED.")
    say("3. Make it rain. In a third Terminal window:")
    say(f'     echo CLOSED > "{folder}/roof.txt"')
    say("   After about a minute the simulated strip cuts outlets 2, 3 and 4 and the session ABORTS.")
    say("4. In the app: ACKNOWLEDGE ABORT, then ALLOW NEW SESSION, then (roof OPEN again) ARM.")
    say(f'     echo OPEN > "{folder}/roof.txt"        # the roof reopens')
    say(f'     cat "{folder}/strip.txt"               # what the simulated strip is doing')
    say("Stop the rehearsal with Ctrl-C. Nothing it did is real.")
    say("")
    try:
        runner.run()
    except KeyboardInterrupt:
        runner.stop()
    say("Rehearsal stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
