#!/usr/bin/env python3
"""Print a per-night summary of the Guardian v1.0 event log (read-only)."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modules.guardian_v1_night_summary import read_events, render, summarize  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", default=str(Path(__file__).resolve().parent / "logs"))
    parser.add_argument("--nights", type=int, default=7,
                        help="how many of the most recent nights to show (default 7)")
    args = parser.parse_args(argv)
    print(render(summarize(read_events(args.log_dir)), last=args.nights))


if __name__ == "__main__":
    main()
