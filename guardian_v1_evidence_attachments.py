"""Offline, non-authorizing evidence attachment inventory for Guardian 1.0.

Does not call CommissioningSession.record_evidence or modify any audit record.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from guardian_v1_evidence_map import CANDIDATES
from modules.commissioning import CommissioningCheck

def make_manifest(fingerprint: str, attachments: dict[str, list[Path]]) -> dict:
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("Expected lowercase SHA-256 configuration fingerprint")
    unknown = set(attachments) - {c.name for c in CommissioningCheck}
    if unknown:
        raise ValueError("Unknown check: " + ", ".join(sorted(unknown)))
    checks = {}
    for check in CommissioningCheck:
        prior, missing = CANDIDATES[check.name]
        files = []
        for path in attachments.get(check.name, []):
            if not path.is_file():
                raise FileNotFoundError(path)
            data = path.read_bytes()
            files.append({
                "file": str(path.resolve()),
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "reviewed": False,
            })
        checks[check.name] = {
            "candidate_evidence": prior,
            "acceptance_gap": missing,
            "attachments": files,
            "review_status": "PENDING",
            "commissioning_result": "NOT_TESTED",
        }
    return {
        "schema": "guardian-evidence-attachment-inventory-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_fingerprint_sha256": fingerprint,
        "checks": checks,
        "verified_count": 0,
        "commissioned": False,
        "hardware_authorized": False,
        "note": "Offline attachment inventory only. Hashes do not establish test validity or authorization.",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--attach", nargs=2, action="append", metavar=("CHECK", "FILE"), default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    attachments = {}
    for check, file in args.attach:
        attachments.setdefault(check, []).append(Path(file))
    payload = json.dumps(make_manifest(args.fingerprint, attachments), indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")

if __name__ == "__main__":
    main()
