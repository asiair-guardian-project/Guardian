"""Read-only commissioning evidence audit; never authorizes live execution."""
import argparse
import hashlib
import json
from pathlib import Path

from guardian_v1_commissioning_preflight import inspect_launchagent
from modules.commissioning import CommissioningCheck, CommissioningResult, CommissioningStatus
from modules.guardian_types import SafetyPowerRole
from modules.guardian_v1_layout import layout_from_installation

def audit(launchagent, kasa_host, installation=None):
    """`installation`: the installation config (with an optional `power` section); None means the Starfront wiring."""
    args = inspect_launchagent(launchagent)
    if not kasa_host:
        raise ValueError("Kasa host required")
    layout = layout_from_installation(installation)
    targets = {t.role.name: {"controller": layout.controller_id, "endpoint": t.endpoint,
                             "outlet": t.number, "alias": t.alias}
               for t in layout.targets}
    if {t.role for t in layout.targets} != {SafetyPowerRole.ASIAIR, SafetyPowerRole.MOUNT, SafetyPowerRole.ACCESSORIES}:
        raise ValueError("Unexpected shutdown roles")
    numbers = [t["outlet"] for t in targets.values()]
    if len(set(numbers)) != 3 or layout.host[0] in numbers:
        raise ValueError("Unsafe outlet topology")
    if layout.starfront and set(numbers) != {2, 3, 4}:
        raise ValueError("Unsafe outlet topology")
    configuration = {
        "asiair_host": args["--asiair-host"],
        "alpaca_host": args["--alpaca-host"],
        "alpaca_port": int(args["--alpaca-port"]),
        "alpaca_device": int(args["--alpaca-device"]),
        "kasa_host": kasa_host,
        "targets": targets,
    }
    if not layout.starfront:                      # Starfront fingerprints stay exactly as before
        configuration["host_outlet"] = {"outlet": layout.host[0], "alias": layout.host[1]}
        configuration["controller_type"] = layout.controller_type
    fingerprint = hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    status = CommissioningStatus(
        results={check: CommissioningResult.NOT_TESTED for check in CommissioningCheck},
        configuration_fingerprint=fingerprint,
    )
    return {
        "configuration": configuration,
        "configuration_fingerprint_sha256": fingerprint,
        "checks": {check.name: status.result_for(check).name for check in CommissioningCheck},
        "commissioned": status.commissioned,
        "hardware_authorized": status.valid_for_configuration(fingerprint),
        "execution_commands": 0,
        "note": "Prior tests do not automatically constitute auditable commissioning evidence.",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launchagent", type=Path, required=True)
    parser.add_argument("--kasa-host", required=True)
    parser.add_argument("--installation-config", type=Path, default=None,
                        help="installation config holding a `power` section; omit for the Starfront wiring")
    args = parser.parse_args()
    installation = None
    if args.installation_config:
        import yaml
        installation = yaml.safe_load(args.installation_config.read_text(encoding="utf-8")) or {}
    print(json.dumps(audit(args.launchagent, args.kasa_host, installation), indent=2))

if __name__ == "__main__":
    main()
