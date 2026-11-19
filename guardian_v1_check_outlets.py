#!/usr/bin/env python3
"""Check your outlet mapping against the real power controller (READ ONLY; switches nothing).

    .venv/bin/python guardian_v1_check_outlets.py --config config/config.yaml

Needs the controller sign-in (Kasa: KASA_USERNAME/KASA_PASSWORD or Keychain; Digital Loggers: DLI_USERNAME/DLI_PASSWORD
or Keychain - see guardian_v1_credentials.py).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules.guardian_v1_layout import layout_from_installation  # noqa: E402
from modules.guardian_v1_outlet_check import run  # noqa: E402
from modules.guardian_v1_outlet_test import real_environment  # noqa: E402
from modules.guardian_v1_setup_config import read_installation  # noqa: E402


def main(argv=None, say=print, read_outlets=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only check of the outlet mapping against the controller")
    parser.add_argument("--config", required=True, help="installation config with kasa.power_strip_ip (+ power section)")
    args = parser.parse_args(argv)
    try:
        installation = read_installation(args.config)
        host = (installation.get("kasa") or {}).get("power_strip_ip")
        if not host:
            say("kasa.power_strip_ip is missing from the config.")
            return 2
        layout = layout_from_installation(installation)
        if read_outlets is None:
            read_outlets = real_environment(host, say=say, layout=layout).read_outlets
    except Exception as error:
        say(f"REFUSED: {error}")
        return 2
    return run(read_outlets, layout, say)


if __name__ == "__main__":
    sys.exit(main())
