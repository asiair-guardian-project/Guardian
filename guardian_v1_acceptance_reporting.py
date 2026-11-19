"""Guardian 1.0 non-authorizing acceptance-test reporting.

Test execution results are not commissioning evidence approval. This module
never writes a CommissioningAuditRecord or modifies hardware authorization.
"""
import argparse
import hashlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from modules.commissioning import CommissioningCheck

SCHEMA = "guardian-acceptance-run-v1"

def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()

def build_report(xml_path: Path, fingerprint: str, *, observed_at: str | None = None) -> dict:
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("fingerprint must be 64 lowercase hexadecimal characters")
    raw = xml_path.read_bytes()
    tree = ET.fromstring(raw)
    if tree.tag == "testsuite":
        suites = [tree]
    elif tree.tag == "testsuites":
        suites = list(tree.findall("testsuite"))
    else:
        raise ValueError("expected pytest JUnit XML testsuite(s)")
    if not suites:
        raise ValueError("JUnit XML has no testsuites")
    cases = []
    for suite in suites:
        for case in suite.iter("testcase"):
            outcome = "PASSED"
            if case.find("failure") is not None:
                outcome = "FAILED"
            elif case.find("error") is not None:
                outcome = "ERROR"
            elif case.find("skipped") is not None:
                outcome = "SKIPPED"
            cases.append({"name": case.get("name", ""), "classname": case.get("classname", ""),
                          "outcome": outcome})
    if not cases:
        raise ValueError("JUnit XML has no testcases")
    counts = {key: sum(c["outcome"] == key for c in cases)
              for key in ("PASSED", "FAILED", "ERROR", "SKIPPED")}
    return {
        "schema": SCHEMA,
        "recorded_at_utc": observed_at or datetime.now(timezone.utc).isoformat(),
        "configuration_fingerprint_sha256": fingerprint,
        "source_junit_xml": str(xml_path.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "test_counts": counts,
        "tests": cases,
        "commissioning_checks": {
            check.name: {"review_status": "PENDING", "commissioning_result": "NOT_TESTED"}
            for check in CommissioningCheck
        },
        "commissioned": False,
        "hardware_authorized": False,
        "notice": "Test execution record only. No evidence acceptance or commissioning authorization.",
    }

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("commissioning_reports"))
    args = parser.parse_args()
    report = build_report(args.junit, args.fingerprint)
    # Timestamp plus content hash gives stable, traceable unique run identity.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output_dir / f"acceptance_{run_id}_{report['source_sha256'][:12]}.json"
    _atomic_json(destination, report)
    saved = json.loads(destination.read_text(encoding="utf-8"))
    if saved != report:
        raise RuntimeError("Report readback verification failed")
    print(f"REPORT_PATH={destination.resolve()}")
    print(f"TEST_COUNTS={json.dumps(report['test_counts'], sort_keys=True)}")
    print("COMMISSIONING_STATUS=NOT_AUTHORIZED")

if __name__ == "__main__":
    main()
