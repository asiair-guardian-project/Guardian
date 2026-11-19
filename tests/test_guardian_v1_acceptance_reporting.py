import json
import xml.etree.ElementTree as ET
import pytest
from guardian_v1_acceptance_reporting import build_report, _atomic_json
from modules.commissioning import CommissioningCheck

FP = "9" * 64

def test_report_counts_and_no_authorization(tmp_path):
    xml = tmp_path / "results.xml"
    xml.write_text('<testsuite><testcase name="ok"/><testcase name="bad"><failure/></testcase><testcase name="skip"><skipped/></testcase></testsuite>')
    report = build_report(xml, FP, observed_at="2026-10-29T17:00:00+00:00")
    assert report["test_counts"] == {"PASSED": 1, "FAILED": 1, "ERROR": 0, "SKIPPED": 1}
    assert report["commissioned"] is False and report["hardware_authorized"] is False
    assert set(report["commissioning_checks"]) == {c.name for c in CommissioningCheck}
    assert all(x["review_status"] == "PENDING" for x in report["commissioning_checks"].values())

def test_atomic_write_readback(tmp_path):
    target = tmp_path / "reports" / "run.json"
    _atomic_json(target, {"ok": True})
    assert json.loads(target.read_text()) == {"ok": True}
    assert not list(target.parent.glob("*.tmp"))

def test_invalid_xml_or_fingerprint_fails_closed(tmp_path):
    xml = tmp_path / "bad.xml"
    xml.write_text("<broken")
    with pytest.raises(ET.ParseError):
        build_report(xml, FP)
    xml.write_text("<testsuite><testcase name='ok'/></testsuite>")
    with pytest.raises(ValueError):
        build_report(xml, "wrong")
    xml.write_text("<testsuite/>")
    with pytest.raises(ValueError):
        build_report(xml, FP)
