"""Read-only Guardian 1.0 commissioning evidence gap report.

This tool never records VERIFIED evidence, changes commissioning state,
or issues hardware commands.
"""
import argparse
import json
from pathlib import Path

from guardian_v1_evidence_audit import audit
from modules.commissioning import CommissioningCheck

REQUIREMENTS = {
    "ASIAIR_MONITORING": "Dated live reachability, failure and stale-data observations",
    "OBSERVATORY_SAFETY": "Dated roof-state, freshness, failure and transition observations",
    "ASIAIR_SAFETY_POWER": "Dated physical outlet 2 VERIFIED_OFF output",
    "MOUNT_SAFETY_POWER": "Dated physical outlet 3 VERIFIED_OFF output",
    "GUARDIAN_SURVIVAL": "Post-shutdown Mac/network continuity evidence",
    "SIMULTANEOUS_PATHS": "Tests covering simultaneous protection-path failures",
    "PROTECTION_LOGIC": "Durable abort, recovery block and no-auto-rearm evidence",
    "ACCESSORIES_SAFETY_POWER": "Dated physical outlet 4 VERIFIED_OFF output",
}

def gap_report(launchagent, kasa_host):
    baseline = audit(launchagent, kasa_host)
    return {
        "configuration_fingerprint_sha256": baseline["configuration_fingerprint_sha256"],
        "commissioned": False,
        "hardware_authorized": False,
        "execution_commands": 0,
        "checks": {
            check.name: {
                "commissioning_result": "NOT_TESTED",
                "required_evidence": REQUIREMENTS[check.name],
                "evidence_attachment": None,
                "review_status": "PENDING",
            }
            for check in CommissioningCheck
        },
        "warning": "Inventory only. No evidence accepted or commissioning authorized.",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launchagent", type=Path, required=True)
    parser.add_argument("--kasa-host", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = gap_report(args.launchagent, args.kasa_host)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")

if __name__ == "__main__":
    main()
