"""Guardian 1.0 armed-capable monitor entry point.

Separate from guardian_v1.py on purpose: guardian_v1.py is the watch-only
entry point and has no way to arm. This file is the only entry point that can
run an armed session, and even here hardware execution stays OFF unless the
launch line carries the exact token  --enable-hardware-execution YES_CUT_POWER.
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guardian 1.0 armed-capable monitor (hardware OFF unless explicitly enabled)",
        allow_abbrev=False,
    )
    parser.add_argument("--recovery-file", default=None)
    parser.add_argument("--operator-socket", default=None)
    parser.add_argument("--installation-config", default=None)
    parser.add_argument("--asiair-host")
    parser.add_argument("--alpaca-host")
    parser.add_argument("--alpaca-port", type=int)
    parser.add_argument("--alpaca-device", type=int, default=17)
    parser.add_argument("--cycle-seconds", type=float, default=5.0)
    parser.add_argument("--kasa-host", default=None,
                        help="HS300 address (must match the installation YAML)")
    parser.add_argument("--commissioning-record", default=None,
                        help="Operator-signed commissioning record (JSON); ARM is refused without a valid one")
    parser.add_argument("--enable-hardware-execution", default=None, metavar="YES_CUT_POWER",
                        help="Exact token that lets this monitor cut power; omit to stay watch-only")
    parser.add_argument("--ups-low-battery-percent", type=int, default=35)
    parser.add_argument("--ups-unreadable-grace-seconds", type=float, default=900.0)
    parser.add_argument("--strip-check-seconds", type=float, default=60.0,
                        help="Seconds between power-strip health checks (the strip dislikes close spacing)")
    parser.add_argument("--asiair-lost-after-misses", type=int, default=2,
                        help="Unanswered ASIAIR pings in a row before it counts as lost")
    parser.add_argument("--alert-level", default="off", choices=["off", "failure", "all"],
                        help="Optional phone alert on abort; off by default")
    return parser


def main() -> None:
    from modules.guardian_v1_armed_launch import run_armed_monitor

    run_armed_monitor(build_parser().parse_args())


if __name__ == "__main__":
    main()
