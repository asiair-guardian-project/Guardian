"""Create or check the operator's commissioning record. Approves nothing itself.

  --output PATH   write a TEMPLATE for this installation: its configuration
                  fingerprint filled in, every check NOT_TESTED, no approver.
                  It refuses to overwrite an existing file. The operator edits
                  the file by hand, marking a check VERIFIED only on their own
                  judgement, and fills in approved_by / approved_at.
  --check PATH    report what Guardian will make of the record (read-only).
"""
import argparse
import json
import os
import sys

from modules.commissioning import CommissioningCheck
from modules.guardian_v1_commissioning_record import SCHEMA, load_commissioning_record
from modules.guardian_v1_configuration_identity import semantic_fingerprint
from modules.guardian_v1_setup_config import read_installation


def build_template(fingerprint):
    return {
        "schema": SCHEMA,
        "configuration_fingerprint": fingerprint,
        "approved_by": "",
        "approved_at": "",
        "results": {check.name: "NOT_TESTED" for check in CommissioningCheck},
    }


def main(argv=None, out=print):
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument("--installation-config", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--output")
    group.add_argument("--check")
    a = p.parse_args(argv)
    fingerprint = semantic_fingerprint(read_installation(a.installation_config))

    if a.output:
        fd = None
        try:
            fd = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            out(f"REFUSED: {a.output} already exists; it is never overwritten.")
            return 2
        with os.fdopen(fd, "w") as handle:
            json.dump(build_template(fingerprint), handle, indent=2)
            handle.write("\n")
        out(f"Template written to {a.output} (every check NOT_TESTED, no approver).")
        out("Edit it yourself. Guardian will refuse ARM until all eight checks are VERIFIED "
            "and approved_by / approved_at are filled in.")
        return 0

    load = load_commissioning_record(a.check, fingerprint)
    out(f"Record: {load.reason}")
    out(f"Usable for ARM: {'YES' if load.usable else 'NO'}")
    if load.approved_by:
        out(f"Approved by {load.approved_by} at {load.approved_at}")
    for check in CommissioningCheck:
        out(f"  {check.name}: {load.status.result_for(check).name}")
    return 0 if load.usable else 1


if __name__ == "__main__":
    sys.exit(main())
