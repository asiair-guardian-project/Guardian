"""First-run setup wizard (step one): read-only checks, one new candidate file, a local-only page."""

import http.client
import json
import os
import re
import stat
import threading
from pathlib import Path

import pytest
import yaml

from modules import guardian_v1_setup_wizard as wizard
from modules.guardian_v1_setup_config import validate_changes
from modules.guardian_v1_setup_web import make_server

GOOD = {"asiair_ip": "192.0.2.10", "roof_host": "alpaca.example.invalid", "roof_port": "443",
        "roof_device": "17", "strip_ip": "192.0.2.20",
        "host_outlet_number": "6", "host_outlet_alias": "Control Mac",
        "asiair_outlet_number": "1", "asiair_outlet_alias": "Air Plus",
        "mount_outlet_number": "2", "mount_outlet_alias": "AM5N",
        "accessories_outlet_number": "3", "accessories_outlet_alias": "Dew Box"}


# ---- building the installation --------------------------------------------------------------

def test_a_good_form_builds_a_complete_validated_installation():
    installation = wizard.build_installation(GOOD)
    assert installation["asiair"]["ip_address"] == "192.0.2.10"
    assert installation["roof"]["alpaca_port"] == 443 and installation["roof"]["alpaca_device_number"] == 17
    assert installation["kasa"]["power_strip_ip"] == "192.0.2.20"
    assert installation["roof"]["source"] == "alpaca" and installation["monitor"]["interval_seconds"] == 5
    validate_changes(installation, {"asiair": {"ip_address": "192.0.2.11"}})      # same rules as the Setup screen
    power = installation["power"]
    assert power["type"] == "kasa_hs300" and power["host_outlet"] == {"number": 6, "alias": "Control Mac"}
    assert power["targets"]["mount"] == {"number": 2, "alias": "AM5N"}
    from modules.guardian_v1_power_mapping import parse_power_section
    from modules.guardian_types import SafetyPowerRole
    assert parse_power_section(power).target_for_role(SafetyPowerRole.ASIAIR).number == 1


@pytest.mark.parametrize("change", [
    {"asiair_ip": "not a host"}, {"asiair_ip": "http://192.0.2.10"}, {"roof_host": ""},
    {"roof_port": "0"}, {"roof_port": "70000"}, {"roof_port": "abc"}, {"roof_device": "-1"},
    {"roof_device": True}, {"strip_ip": "10.0.0.1/24"}, {"strip_ip": 5},
    {"mount_outlet_number": "1"},                      # the same outlet as the ASIAIR
    {"mount_outlet_number": "6"},                      # the computer's own outlet
    {"mount_outlet_number": "0"}, {"mount_outlet_number": "7"}, {"mount_outlet_number": "two"},
    {"mount_outlet_alias": "air plus"},                # the same name as another outlet, other case
    {"mount_outlet_alias": ""}, {"host_outlet_alias": 5},
])
def test_bad_values_are_refused(change):
    with pytest.raises(wizard.WizardError):
        wizard.build_installation({**GOOD, **change})


def test_missing_and_unknown_fields_are_refused():
    for field in ("strip_ip", "host_outlet_alias", "accessories_outlet_number"):
        partial = dict(GOOD)
        del partial[field]
        with pytest.raises(wizard.WizardError):
            wizard.build_installation(partial)
    with pytest.raises(wizard.WizardError):
        wizard.build_installation({**GOOD, "folder": "/tmp"})
    with pytest.raises(wizard.WizardError):
        wizard.build_installation("not a mapping")


# ---- the read-only checks --------------------------------------------------------------------

def test_asiair_check_reports_without_raising():
    assert wizard.check_asiair("192.0.2.10", ping=lambda host: True)["ok"] is True
    assert wizard.check_asiair("192.0.2.10", ping=lambda host: False)["ok"] is False

    def broken(host):
        raise FileNotFoundError("ping not found")
    assert wizard.check_asiair("192.0.2.10", ping=broken)["ok"] is False


def test_an_invalid_address_is_reported_without_touching_the_network():
    calls = []
    assert wizard.check_asiair("bad host", ping=lambda h: calls.append(h) or True)["ok"] is False
    assert wizard.check_roof("bad host", 443, 17, reader=lambda *a, **k: calls.append(a))["ok"] is False
    assert wizard.check_strip("bad host", ping=lambda h: calls.append(h) or True)["ok"] is False
    assert calls == []


def test_roof_check_says_what_it_read_and_never_what_to_do():
    safe = wizard.check_roof("h.example", 443, 17, reader=lambda *a, **k: {"is_safe": True})
    shut = wizard.check_roof("h.example", "443", "17", reader=lambda *a, **k: {"is_safe": False})
    assert safe["ok"] and "SAFE" in safe["detail"] and "NOT SAFE" not in safe["detail"]
    assert shut["ok"] and "NOT SAFE" in shut["detail"]
    unclear = wizard.check_roof("h.example", 443, 17, reader=lambda *a, **k: {"is_safe": "maybe"})
    assert unclear["ok"] is False

    def broken(*a, **k):
        raise RuntimeError("timed out")
    assert wizard.check_roof("h.example", 443, 17, reader=broken)["ok"] is False


def test_the_roof_check_passes_the_operators_values_through():
    seen = {}

    def reader(host, port, device, timeout_seconds):
        seen.update(host=host, port=port, device=device)
        return {"is_safe": True}
    wizard.check_roof("h.example", "8443", "21", reader=reader)
    assert seen == {"host": "h.example", "port": 8443, "device": 21}


def test_strip_check_is_a_ping_and_nothing_else():
    asked = []
    assert wizard.check_strip("192.0.2.20", ping=lambda host: asked.append(host) or True)["ok"] is True
    assert asked == ["192.0.2.20"]
    assert wizard.check_strip("192.0.2.20", ping=lambda host: False)["ok"] is False

    def broken(host):
        raise FileNotFoundError("ping not found")
    assert wizard.check_strip("192.0.2.20", ping=broken)["ok"] is False


def test_strip_check_never_opens_a_connection_to_the_strip(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("the strip check must not open a connection")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert wizard.check_strip("192.0.2.20", ping=lambda host: True)["ok"] is True


# ---- the only write --------------------------------------------------------------------------

def test_the_candidate_file_is_new_private_and_valid(tmp_path):
    result = wizard.write_candidate(tmp_path, wizard.build_installation(GOOD))
    path = Path(result["path"])
    assert path == tmp_path / wizard.CANDIDATE_NAME
    assert result["activated"] is False and result["commissioning_authorized"] is False
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert yaml.safe_load(path.read_text()) == wizard.build_installation(GOOD)


def test_an_existing_file_is_never_overwritten(tmp_path):
    existing = tmp_path / wizard.CANDIDATE_NAME
    existing.write_text("precious")
    with pytest.raises(wizard.WizardError):
        wizard.write_candidate(tmp_path, wizard.build_installation(GOOD))
    assert existing.read_text() == "precious"


def test_a_symlink_in_the_way_is_refused_and_its_target_untouched(tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text("keep")
    (tmp_path / wizard.CANDIDATE_NAME).symlink_to(target)
    with pytest.raises(wizard.WizardError):
        wizard.write_candidate(tmp_path, wizard.build_installation(GOOD))
    assert target.read_text() == "keep"


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(wizard.WizardError):
        wizard.write_candidate(tmp_path / "nope", wizard.build_installation(GOOD))


def test_a_failed_write_leaves_no_partial_file(tmp_path, monkeypatch):
    def broken(_descriptor):
        raise OSError("disk full")
    monkeypatch.setattr(wizard.os, "fsync", broken)
    with pytest.raises(OSError):
        wizard.write_candidate(tmp_path, wizard.build_installation(GOOD))
    assert not (tmp_path / wizard.CANDIDATE_NAME).exists()


# ---- the local-only page ---------------------------------------------------------------------

@pytest.fixture
def served(tmp_path):
    ran = []
    server = make_server(tmp_path, port=0, checks={
        "asiair": lambda body: ran.append(("asiair", body)) or {"ok": True, "detail": "stub"},
        "strip": lambda body: (_ for _ in ()).throw(RuntimeError("boom")),
    })
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, tmp_path, ran
    server.shutdown()
    server.server_close()


def call(server, method, path, body=None, *, token="", host=None, content_type="application/json", raw=None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if token is not None and method == "POST":
        headers["X-Wizard-Token"] = token
    payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    if method == "POST":
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(payload))
    connection.request(method, path, body=payload if method == "POST" else None, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data, response


def test_it_listens_on_the_loopback_address_only(served):
    server, _, _ = served
    assert server.server_address[0] == "127.0.0.1"


def test_the_page_carries_the_token_and_a_strict_content_policy(served):
    server, _, _ = served
    status, data, response = call(server, "GET", "/")
    assert status == 200 and server.guardian_token.encode() in data
    assert "default-src 'none'" in response.getheader("Content-Security-Policy")
    assert b"http://" not in data.replace(b"http://127", b"")        # nothing is loaded from elsewhere


def test_a_foreign_host_header_is_refused(served):
    server, _, _ = served
    assert call(server, "GET", "/", host="evil.example")[0] == 400
    assert call(server, "POST", "/api/check", {"which": "asiair"}, token=server.guardian_token,
                host="evil.example")[0] == 400


def test_posts_need_the_token_and_a_json_body(served):
    server, folder, ran = served
    good = {"which": "asiair"}
    assert call(server, "POST", "/api/check", good, token="")[0] == 403
    assert call(server, "POST", "/api/check", good, token="wrong")[0] == 403
    assert call(server, "POST", "/api/check", good, token=server.guardian_token,
                content_type="text/plain")[0] == 415
    assert call(server, "POST", "/api/check", raw=b"x" * 5000, token=server.guardian_token)[0] == 413
    assert call(server, "POST", "/api/check", raw=b"{not json", token=server.guardian_token)[0] == 400
    assert call(server, "POST", "/api/check", [1, 2], token=server.guardian_token)[0] == 400
    assert ran == []
    assert not any(folder.iterdir())                                  # nothing ran, nothing written


def test_unknown_routes_and_checks_are_refused(served):
    server, _, _ = served
    token = server.guardian_token
    assert call(server, "GET", "/api/write")[0] == 404
    assert call(server, "POST", "/api/arm", {}, token=token)[0] == 404
    assert call(server, "POST", "/api/check", {"which": "arm"}, token=token)[0] == 400
    assert call(server, "POST", "/api/check", {"which": "power_off"}, token=token)[0] == 400


def test_a_check_runs_and_a_crashing_check_is_only_a_report(served):
    server, _, ran = served
    token = server.guardian_token
    status, data, _ = call(server, "POST", "/api/check", {"which": "asiair", "asiair_ip": "192.0.2.10"}, token=token)
    assert status == 200 and json.loads(data) == {"ok": True, "detail": "stub"} and ran
    status, data, _ = call(server, "POST", "/api/check", {"which": "strip"}, token=token)
    assert status == 200 and json.loads(data)["ok"] is False


def test_writing_creates_one_candidate_in_the_folder_chosen_at_startup(served):
    server, folder, _ = served
    token = server.guardian_token
    status, data, _ = call(server, "POST", "/api/write",
                           {"form": GOOD, "folder": "/tmp/somewhere-else"}, token=token)
    reply = json.loads(data)
    assert status == 200 and reply["ok"] is True and reply["activated"] is False
    assert [p.name for p in folder.iterdir()] == [wizard.CANDIDATE_NAME]
    assert not Path("/tmp/somewhere-else").exists()
    again = json.loads(call(server, "POST", "/api/write", {"form": GOOD}, token=token)[1])
    assert again["ok"] is False and "refusing to overwrite" in again["message"]


def test_the_form_cannot_name_a_folder(served):
    server, folder, _ = served
    reply = json.loads(call(server, "POST", "/api/write", {"form": {**GOOD, "folder": "/tmp/x"}},
                            token=server.guardian_token)[1])
    assert reply["ok"] is False and not any(folder.iterdir())


def test_bad_values_write_nothing(served):
    server, folder, _ = served
    reply = json.loads(call(server, "POST", "/api/write", {"form": {**GOOD, "roof_port": "0"}},
                            token=server.guardian_token)[1])
    assert reply["ok"] is False and not any(folder.iterdir())


def test_the_wizard_has_no_way_to_arm_disarm_or_switch_power():
    forbidden = [r"operator_socket", r"guardian_v1_operator", r"SafetyPowerManager", r"power_off",
                 r"connect_hs300", r"\bARM\b", r"\bDISARM\b", r"RELEASE_ABORT", r"\bsendall\b", r"(?<![_\w])send\("]
    for name in ("guardian_v1_setup_wizard.py", "guardian_v1_setup_web.py"):
        source = (Path(__file__).resolve().parent.parent / "modules" / name).read_text()
        code = re.sub(r'''""".*?"""''', "", source, flags=re.S)            # prose may name what is NOT done
        code = re.sub(r"^\s*#.*$", "", code, flags=re.M)
        # the page's visible text may say what it does not do; only Python code is checked
        code = code[: code.index("_PAGE = ")] if "_PAGE = " in code else code
        found = [pattern for pattern in forbidden if re.search(pattern, code)]
        assert found == [], (name, found)


# ---- the page itself -------------------------------------------------------------------------

def test_no_button_calls_a_function_that_the_browser_resolves_to_a_document_method():
    # Inline click handlers see `document` first, so a page function named write() would call document.write().
    from modules.guardian_v1_setup_web import _page
    html = _page("tok").decode()
    called = set(re.findall(r'onclick="([A-Za-z_]\w*)\(', html))
    assert called, "no buttons found"
    document_methods = {"write", "writeln", "open", "close", "clear", "focus", "execCommand", "getSelection", "hasFocus"}
    assert called.isdisjoint(document_methods), called & document_methods
    for name in called:
        assert re.search(rf"function {name}\(", html), f"{name} is not defined in the page"


def test_the_page_works_in_a_real_browser():
    import shutil
    playwright = pytest.importorskip("playwright.sync_api")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        pytest.skip("no Chrome or Chromium here")
    import tempfile
    folder = Path(tempfile.mkdtemp())
    server = make_server(folder, port=0, checks={
        "asiair": lambda body: {"ok": True, "detail": "stub ping"},
        "roof": lambda body: {"ok": True, "detail": "stub roof"},
        "strip": lambda body: {"ok": False, "detail": "stub strip down"},
    })
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
            page.click('button:has-text("Start")')
            page.fill("#asiair_ip", "192.0.2.10")
            page.click("#s1 >> text=Check (ping)")
            page.wait_for_selector("#r_asiair.ok")
            page.click("#s1 >> text=Next")
            page.fill("#roof_device", "17")
            page.click("#s2 >> text=Next")
            page.fill("#strip_ip", "192.0.2.20")
            page.click("#s3 >> text=Check (ping)")
            page.wait_for_selector("#r_strip.bad")
            page.click("#s3 >> text=Next")
            for field in ("host_outlet", "asiair_outlet", "mount_outlet", "accessories_outlet"):
                page.fill(f"#{field}_number", {"host_outlet": "6", "asiair_outlet": "1", "mount_outlet": "2",
                                                 "accessories_outlet": "3"}[field])
                page.fill(f"#{field}_alias", {"host_outlet": "Control Mac", "asiair_outlet": "Air Plus",
                                                "mount_outlet": "AM5N", "accessories_outlet": "Dew Box"}[field])
            page.click("#s4 >> text=Next")
            page.click("#wr")
            page.wait_for_selector("#r_write.ok")
            assert "nothing activated" in page.inner_text("#r_write")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    assert errors == []
    assert [p.name for p in folder.iterdir()] == [wizard.CANDIDATE_NAME]


def test_the_final_screen_warns_not_to_overwrite_an_existing_configuration():
    steps = " ".join(wizard.next_steps("/x/config.guardian-candidate.yaml"))
    assert "do NOT copy this file over" in steps and "only the four" in steps


def test_spaces_typed_around_a_name_are_trimmed_so_the_stored_name_is_exact():
    installation = wizard.build_installation({**GOOD, "mount_outlet_alias": "  AM5N  "})
    assert installation["power"]["targets"]["mount"]["alias"] == "AM5N"
