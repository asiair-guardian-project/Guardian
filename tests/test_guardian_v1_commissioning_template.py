import json

import yaml

from guardian_v1_commissioning_template import build_template, main
from modules.commissioning import CommissioningCheck
from modules.guardian_v1_configuration_identity import semantic_fingerprint
from tests.test_guardian_v1_armed_launch import INSTALLATION


def cfg(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(INSTALLATION))
    return str(p)


def test_template_has_no_verified_check_and_no_approver(tmp_path):
    out = tmp_path / "rec.json"
    assert main(["--installation-config", cfg(tmp_path), "--output", str(out)], out=lambda _l: None) == 0
    data = json.loads(out.read_text())
    assert set(data["results"].values()) == {"NOT_TESTED"}
    assert set(data["results"]) == {c.name for c in CommissioningCheck}
    assert data["approved_by"] == "" and data["approved_at"] == ""
    assert data["configuration_fingerprint"] == semantic_fingerprint(INSTALLATION)
    assert oct(out.stat().st_mode & 0o777) == "0o600"


def test_unedited_template_is_not_usable_for_arm(tmp_path):
    out = tmp_path / "rec.json"
    main(["--installation-config", cfg(tmp_path), "--output", str(out)], out=lambda _l: None)
    lines = []
    assert main(["--installation-config", cfg(tmp_path), "--check", str(out)], out=lines.append) == 1
    assert any("Usable for ARM: NO" in line for line in lines)


def test_never_overwrites_an_existing_file(tmp_path):
    out = tmp_path / "rec.json"
    out.write_text("keep me")
    assert main(["--installation-config", cfg(tmp_path), "--output", str(out)], out=lambda _l: None) == 2
    assert out.read_text() == "keep me"


def test_hand_completed_record_is_recognised_as_usable(tmp_path):
    out = tmp_path / "rec.json"
    data = build_template(semantic_fingerprint(INSTALLATION))
    data.update(approved_by="Operator", approved_at="2026-11-02T12:00:00Z",
                results={c.name: "VERIFIED" for c in CommissioningCheck})
    out.write_text(json.dumps(data))
    out.chmod(0o600)
    lines = []
    assert main(["--installation-config", cfg(tmp_path), "--check", str(out)], out=lines.append) == 0
    assert any("Usable for ARM: YES" in line for line in lines)


def test_tool_has_no_way_to_mark_a_check_verified():
    from pathlib import Path
    source = Path("guardian_v1_commissioning_template.py").read_text()
    assert source.count("VERIFIED") <= 2  # docstring text only
    assert '"VERIFIED"' not in source
