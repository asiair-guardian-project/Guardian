"""Read-only outlet-name check against the controller, and the Keychain credentials helper."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from dli_fake import FakeDli  # noqa: E402

import guardian_v1_check_outlets as check_cli  # noqa: E402
import guardian_v1_credentials as cred_cli  # noqa: E402
from modules import guardian_v1_credentials as cred  # noqa: E402
from modules.guardian_v1_dli_transport import DigitalLoggersTransport  # noqa: E402
from modules.guardian_v1_layout import layout_from_installation, starfront_layout  # noqa: E402
from modules.guardian_v1_outlet_check import compare, run  # noqa: E402
from modules.guardian_v1_outlet_test import real_environment_dli  # noqa: E402

KASA = {"power": {"type": "kasa_hs300", "host_outlet": {"number": 6, "alias": "Control Mac"},
                  "targets": {"asiair": {"number": 1, "alias": "Air Plus"}, "mount": {"number": 2, "alias": "AM5N"},
                              "accessories": {"number": 3, "alias": "Dew Box"}}}}


def strip(names, on=(1, 2, 3, 4, 5, 6)):
    return [{"number": n, "name": name, "is_on": n in on, "protected": False} for n, name in names.items()]


GOOD = {1: "Air Plus", 2: "AM5N", 3: "Dew Box", 4: "Spare4", 5: "Spare5", 6: "Control Mac"}


def test_matching_names_pass_and_nothing_is_switched():
    lines = []
    assert run(lambda: strip(GOOD), layout_from_installation(KASA), lines.append) == 0
    assert any("All mapped outlet names match" in l for l in lines)


@pytest.mark.parametrize("bad,expect", [
    ({**GOOD, 2: "am5n"}, "DOES NOT MATCH"),
    ({**GOOD, 6: "Mac"}, "DOES NOT MATCH"),
    ({**GOOD, 4: "AM5N"}, "NOT UNIQUE"),
])
def test_wrong_or_duplicate_names_fail(bad, expect):
    lines = []
    assert run(lambda: strip(bad), layout_from_installation(KASA), lines.append) == 1
    assert any(expect in l for l in lines)


def test_an_outlet_the_controller_does_not_have_fails():
    lines = []
    assert run(lambda: strip({1: "Air Plus", 2: "AM5N", 3: "Dew Box"}), layout_from_installation(KASA),
               lines.append) == 1
    assert any("NOT FOUND" in l for l in lines)


def test_an_unreadable_controller_fails_with_a_message():
    def boom():
        raise RuntimeError("no route to host")
    lines = []
    assert run(boom, layout_from_installation(KASA), lines.append) == 1 and "no route" in lines[0]


def test_starfront_layout_checks_the_fixed_names():
    names = {1: "Mac Mini", 2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus", 5: "spare", 6: "Plug 6"}
    assert run(lambda: strip(names), starfront_layout(), lambda s: None) == 0


def test_cli_reads_a_simulated_digital_loggers_unit_and_sends_only_reads(tmp_path):
    import yaml
    fake = FakeDli(["Mac", "ASIAIR", "Mount", "Dew", "s5", "s6", "s7", "s8"]).start()
    try:
        installation = {"kasa": {"power_strip_ip": "127.0.0.1"},
                        "power": {"type": "digital_loggers_rest", "host_outlet": {"number": 1, "alias": "Mac"},
                                  "targets": {"asiair": {"number": 2, "alias": "ASIAIR"},
                                              "mount": {"number": 3, "alias": "Mount"},
                                              "accessories": {"number": 4, "alias": "Dew"}}}}
        path = tmp_path / "c.yaml"
        path.write_text(yaml.safe_dump(installation))
        layout = layout_from_installation(installation)
        transport = DigitalLoggersTransport(host="127.0.0.1", port=fake.port, username="admin", password="secret")
        env = real_environment_dli("127.0.0.1", layout, 5, transport=transport)
        lines = []
        assert check_cli.main(["--config", str(path)], say=lines.append, read_outlets=env.read_outlets) == 0
        assert not [1 for m, p, f in fake.log if m != "GET"]
    finally:
        fake.stop()


def test_the_check_cannot_switch_anything():
    root = Path(__file__).resolve().parent.parent
    for name in ("guardian_v1_check_outlets.py", "modules/guardian_v1_outlet_check.py"):
        code = (root / name).read_text().split('"""', 2)[2]
        assert not re.search(r"power_off|switch_on|set_outlet_power|PUT|\.request\(", code), name


# ---- credentials ------------------------------------------------------------------------------

def test_set_never_puts_the_password_anywhere_in_the_commands():
    calls = []
    cred.set_credentials("kasa", "me@example.com", run=lambda c: calls.append(list(c)) or 0)
    assert calls[0][-2:] == ["-w", "me@example.com"]
    assert calls[1][-1] == "-w" and "Guardian Kasa Password" in calls[1]        # no value: macOS prompts
    assert all(c[0] == "security" and "-a" in c and "guardian" in c for c in calls)


def test_dli_uses_its_own_keychain_items_which_the_transport_reads():
    calls = []
    cred.set_credentials("dli", "admin", run=lambda c: calls.append(list(c)) or 0)
    services = [c[c.index("-s") + 1] for c in calls]
    assert services == ["Guardian Digital Loggers Username", "Guardian Digital Loggers Password"]
    import modules.guardian_v1_dli_transport as t
    source = Path(t.__file__).read_text()
    assert all(s in source for s in services)


def test_kasa_items_match_what_the_kasa_controller_reads():
    source = (Path(__file__).resolve().parent.parent / "modules" / "kasa_controller.py").read_text()
    assert all(s in source for s in cred.SERVICES["kasa"])


def test_a_failed_or_cancelled_save_is_reported():
    with pytest.raises(cred.CredentialError):
        cred.set_credentials("kasa", "me", run=lambda c: 1)
    answers = iter([0, 1])
    with pytest.raises(cred.CredentialError):
        cred.set_credentials("kasa", "me", run=lambda c: next(answers))


@pytest.mark.parametrize("name", ["", "  ", "a\nb"])
def test_bad_user_names_are_refused_before_anything_runs(name):
    calls = []
    with pytest.raises(cred.CredentialError):
        cred.set_credentials("kasa", name, run=lambda c: calls.append(c) or 0)
    assert calls == []


def test_check_reports_presence_and_never_asks_for_the_secret():
    calls = []
    found = cred.check_credentials("kasa", run=lambda c: calls.append(list(c)) or 0)
    assert found == {"username": True, "password": True}
    assert all("-w" not in c and "-g" not in c for c in calls)
    missing = cred.check_credentials("dli", run=lambda c: 44)
    assert missing == {"username": False, "password": False}


def test_cli_set_and_check(tmp_path):
    lines = []
    assert cred_cli.main(["set", "kasa"], say=lines.append, ask=lambda p: "me@example.com", run=lambda c: 0) == 0
    assert cred_cli.main(["check", "kasa"], say=lines.append, run=lambda c: 0) == 0
    assert cred_cli.main(["check", "dli"], say=lines.append, run=lambda c: 44) == 1
    assert any("password saved: yes" in l for l in lines)


def test_the_credentials_helper_never_reads_a_password():
    root = Path(__file__).resolve().parent.parent
    for name in ("guardian_v1_credentials.py", "modules/guardian_v1_credentials.py"):
        code = (root / name).read_text().split('"""', 2)[2]
        assert not re.search(r"getpass|input\(.*[Pp]assword|find-generic-password.*-w|capture_output", code), name
