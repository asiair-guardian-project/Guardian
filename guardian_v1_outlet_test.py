"""Live test of Guardian 1.0's power-off path on ONE spare outlet.

Starfront wiring (no `power` section in the installation config): outlet 5 only.
With your own outlet mapping: any outlet that nothing is mapped to; give it with --outlet.

    .venv/bin/python guardian_v1_outlet_test.py list
    .venv/bin/python guardian_v1_outlet_test.py test --expect-alias "<name of the spare outlet>" [--outlet N]
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from modules.guardian_v1_layout import layout_from_installation  # noqa: E402
from modules.guardian_v1_outlet_test import (  # noqa: E402
    TEST_OUTLET, list_outlets, real_environment, run_test)
from modules.guardian_v1_stage_b import StageBError, read_plist, V1_LABEL  # noqa: E402


def kasa_host_from_monitor_plist():
    plist = read_plist(Path.home() / "Library" / "LaunchAgents" / f"{V1_LABEL}.plist")
    args = [str(a) for a in plist["ProgramArguments"]]
    if "--kasa-host" in args and args.index("--kasa-host") + 1 < len(args):
        return args[args.index("--kasa-host") + 1]
    raise StageBError("No --kasa-host in the v1.0 monitor launchd file; pass --kasa-host")


def layout_from_monitor_plist():
    """The layout the live monitor uses: its installation config's `power` section, else the Starfront wiring."""
    plist = read_plist(Path.home() / "Library" / "LaunchAgents" / f"{V1_LABEL}.plist")
    args = [str(a) for a in plist["ProgramArguments"]]
    if "--installation-config" in args and args.index("--installation-config") + 1 < len(args):
        import yaml
        path = Path(args[args.index("--installation-config") + 1])
        if path.exists():
            return layout_from_installation(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return layout_from_installation({})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Guardian 1.0 spare-outlet live test")
    parser.add_argument("action", choices=["list", "test"])
    parser.add_argument("--outlet", type=int, default=None,
                        help="the spare outlet to test (Starfront wiring: only 5, the default)")
    parser.add_argument("--expect-alias", default=None, help="the exact name of the spare outlet (see 'list')")
    parser.add_argument("--pause", action="store_true",
                        help="stop after each switch so you can check outlet 5 in the Kasa app")
    parser.add_argument("--kasa-host", default=None, help="default: taken from the v1.0 monitor launchd file")
    args = parser.parse_args(argv)

    try:
        host = args.kasa_host or kasa_host_from_monitor_plist()
        layout = layout_from_monitor_plist()
        outlet = args.outlet if args.outlet is not None else (TEST_OUTLET if layout.starfront else None)
        if outlet is not None and outlet not in layout.allowed_test_outlets():
            print(f"REFUSED: outlet {outlet} cannot be tested here. Outlets Guardian uses are protected; spare "
                  f"outlets you may test: {list(layout.allowed_test_outlets()) or 'none'}. Nothing was contacted.")
            return 1
        env = real_environment(host, say=lambda text: print(text, flush=True),
                               outlet_number=outlet or TEST_OUTLET, layout=layout)
        if args.action == "list":
            return list_outlets(env)
        if outlet is None:
            print("REFUSED: your outlet mapping is in use, so say which spare outlet to test with --outlet "
                  f"(spare outlets: {list(layout.allowed_test_outlets())}; run 'list' first).")
            return 1
        if not args.expect_alias:
            print(f"REFUSED: 'test' needs --expect-alias with the exact name of outlet {outlet} (run 'list' first).")
            return 1
        return run_test(env, outlet, args.expect_alias, pause=args.pause, layout=layout)
    except StageBError as exc:
        print(f"REFUSED: {exc}")
        return 1
    except Exception as exc:
        print(f"FAILED before anything was switched: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
