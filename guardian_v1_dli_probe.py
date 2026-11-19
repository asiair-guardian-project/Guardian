#!/usr/bin/env python3
"""Read-only check of a Digital Loggers controller against Guardian's power mapping.

Sends only GET requests. Never switches anything. Use it before relying on Digital Loggers support, which has not
been tested on real hardware: it shows what the controller actually answers and whether each mapped outlet's name
matches. Credentials: DLI_USERNAME / DLI_PASSWORD, or the macOS Keychain (see the setup page's next steps).

    python guardian_v1_dli_probe.py --config config.guardian-candidate.yaml
"""
import argparse
import sys

import yaml

from modules.guardian_v1_dli_transport import DigitalLoggersTransport, DliTransportError, dli_credentials
from modules.guardian_v1_power_mapping import PowerMappingError, parse_power_section


def main(argv=None, transport=None, out=print):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", required=True, help="a config file with kasa.power_strip_ip and a power section")
    args = ap.parse_args(argv)
    with open(args.config, encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    try:
        mapping = parse_power_section(config.get("power"))
    except PowerMappingError as error:
        out(f"The power section is not usable: {error}")
        return 2
    if mapping.controller_type != "digital_loggers_rest":
        out("This probe is for power.type digital_loggers_rest only.")
        return 2
    host = (config.get("kasa") or {}).get("power_strip_ip")
    if not host:
        out("kasa.power_strip_ip is missing.")
        return 2
    try:
        if transport is None:
            username, password = dli_credentials()
            transport = DigitalLoggersTransport(host=host, username=username, password=password,
                                                port=mapping.options.get("port"),
                                                scheme=mapping.options.get("scheme", "http"))
        rows = transport.survey()
    except DliTransportError as error:
        out(f"Could not read the controller: {error}")
        return 1
    out("Read-only survey (nothing was switched):")
    for number, name, state, problem in rows:
        shown = "?" if state is None else state.name
        out(f"  outlet {number}: name={name!r} state={shown}" + (f"  PROBLEM: {problem}" if problem else ""))
    by_number = {row[0]: row for row in rows}
    roles = [("this computer", mapping.host_outlet)] + [(n, o) for n, o in mapping.targets.items()]
    bad = 0
    out("Your mapping:")
    for role, outlet in roles:
        row = by_number.get(outlet.number)
        ok = bool(row and row[1] == outlet.alias and row[3] is None)
        bad += not ok
        out(f"  {role}: outlet {outlet.number} {outlet.alias!r} -> " +
            ("matches" if ok else f"DOES NOT MATCH (controller says {row[1] if row else None!r})"))
    out("All mapped outlets match." if not bad else f"{bad} mapped outlet(s) do not match; do not rely on this mapping.")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
