import plistlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

from modules import guardian_v1_stage_b as sb
from modules.guardian_v1_stage_b import (
    CONFIRM_PHRASE, HARDWARE_FLAG, HARDWARE_TOKEN, Environment, StageBError)

V1 = sb.V1_LABEL
V06 = sb.V06_LABEL


class FakeSystem:
    """A small stand-in for launchd, v0.6 and the v1.0 monitor."""

    def __init__(self, tmp_path, hardware=False, v06_alive=True, v06_protection="DISARMED",
                 v1_armed=False, v06_loaded=True, v06_disabled=False, with_record=True, has_v06=True):
        self.dir = tmp_path
        self.agents = tmp_path / "LaunchAgents"
        self.agents.mkdir()
        self.record = tmp_path / "commissioning.json"
        if with_record:
            self.record.write_text("{}")
        args = ["/py", "/proj/guardian_v1_armed.py",
                "--recovery-file", "/r", "--operator-socket", "/s",
                "--installation-config", "/i", "--kasa-host", "10.0.0.5",
                "--commissioning-record", str(self.record)]
        if hardware:
            args += [HARDWARE_FLAG, HARDWARE_TOKEN]
        (self.agents / f"{V1}.plist").write_bytes(plistlib.dumps({"Label": V1, "ProgramArguments": args}))
        if has_v06:
            (self.agents / f"{V06}.plist").write_bytes(
                plistlib.dumps({"Label": V06, "ProgramArguments": ["/py", "main.py"]}))
        self.loaded = {V1}
        if v06_loaded and has_v06:
            self.loaded.add(V06)
        self.disabled = {V06} if v06_disabled else set()
        self.v06_alive = v06_alive
        self.v06_protection = v06_protection
        self.v1_hardware = hardware
        self.v1_armed = v1_armed
        self.v1_up = True
        self.calls = []
        self.output = []
        self.answers = [CONFIRM_PHRASE]
        self.fail = set()          # launchctl verbs to fail
        self.v1_never_returns = False
        self.v06_wont_stop = False
        self.lint_fails = False
        self.bootstrap_fail_times = 0   # fail this many v1.0 bootstraps with an I/O error (launchd still unloading)
        self.bootstrap_errors = 0
        self.linger_lists = 0           # after a v1.0 bootout, keep listing it for this many `list` calls

    # --- environment callables
    def run(self, cmd):
        self.calls.append(list(cmd))
        if cmd[0] == "plutil":
            if self.lint_fails:
                return 1, "bad plist"
            try:
                plistlib.loads(Path(cmd[2]).read_bytes())
            except Exception as exc:
                return 1, str(exc)
            return 0, "OK"
        verb = cmd[1]
        if verb in self.fail:
            return 1, f"{verb} failed"
        if verb == "list":
            if self.linger_lists > 0:
                self.linger_lists -= 1
                return 0, "".join(f"123\t0\t{label}\n" for label in sorted(self.loaded | {V1}))
            return 0, "".join(f"123\t0\t{label}\n" for label in sorted(self.loaded))
        if verb == "print-disabled":
            return 0, "".join(f'\t"{l}" => disabled\n' for l in sorted(self.disabled)) + '\t"other" => enabled\n'
        if verb == "bootout":
            label = cmd[2].rsplit("/", 1)[1]
            self.loaded.discard(label)
            if label == V06 and not self.v06_wont_stop:
                self.v06_alive = False
            if label == V1:
                self.v1_up = False
            return 0, ""
        if verb == "disable":
            self.disabled.add(cmd[2].rsplit("/", 1)[1]); return 0, ""
        if verb == "enable":
            self.disabled.discard(cmd[2].rsplit("/", 1)[1]); return 0, ""
        if verb == "bootstrap":
            if cmd[3].endswith(f"{V1}.plist") and self.linger_lists > 0:
                self.bootstrap_errors += 1
                return 5, "Bootstrap failed: 5: Input/output error"
            if cmd[3].endswith(f"{V1}.plist") and self.bootstrap_fail_times > 0:
                self.bootstrap_fail_times -= 1
                return 5, "Bootstrap failed: 5: Input/output error"
            path = Path(cmd[3])
            label = plistlib.loads(path.read_bytes())["Label"]
            self.loaded.add(label)
            if label == V06:
                self.v06_alive, self.v06_protection = True, "DISARMED"
            if label == V1:
                args = plistlib.loads(path.read_bytes())["ProgramArguments"]
                hardware = HARDWARE_FLAG in args
                # the real launcher refuses hardware while v0.6 is running
                if hardware and self.v06_alive:
                    self.v1_up = False
                elif self.v1_never_returns:
                    self.v1_up = False
                else:
                    self.v1_up, self.v1_hardware, self.v1_armed = True, hardware, False
            return 0, ""
        raise AssertionError(f"unexpected command {cmd}")

    def v1_status(self):
        if not self.v1_up:
            return None
        return {"connected": True, "armed": self.v1_armed,
                "hardware_execution_enabled": self.v1_hardware}

    def v06_state(self):
        return {"alive": self.v06_alive, "pid": 99 if self.v06_alive else None,
                "protection": self.v06_protection if self.v06_alive else None}

    def env(self):
        return Environment(
            uid=501, v1_plist=self.agents / f"{V1}.plist", v06_plist=self.agents / f"{V06}.plist",
            backup_dir=self.dir / "backups", run=self.run, v1_status=self.v1_status,
            v06_state=self.v06_state, say=self.output.append,
            confirm=lambda prompt: self.answers.pop(0) if self.answers else "",
            sleep=lambda s: None, now=lambda: datetime(2026, 11, 14, 7, 0, 0),
            file_exists=lambda p: Path(p).exists())

    def v1_args(self):
        return plistlib.loads((self.agents / f"{V1}.plist").read_bytes())["ProgramArguments"]

    def verbs(self):
        return [c[1] for c in self.calls if c[0] == "launchctl"]

    def changed_anything(self):
        return any(v in ("bootout", "bootstrap", "enable", "disable") for v in self.verbs())


# ---- plist editing -----------------------------------------------------------

def test_with_and_without_hardware_are_exact_opposites():
    plist = {"ProgramArguments": ["/py", "/p/guardian_v1_armed.py", "--a", "1"]}
    on = sb.with_hardware(plist)
    assert on["ProgramArguments"][-2:] == [HARDWARE_FLAG, HARDWARE_TOKEN]
    assert plist["ProgramArguments"][-1] == "1"            # input not modified
    assert sb.without_hardware(on)["ProgramArguments"] == plist["ProgramArguments"]


def test_refuses_to_edit_the_wrong_program_or_double_enable():
    with pytest.raises(StageBError):
        sb.with_hardware({"ProgramArguments": ["/py", "/p/guardian_v1.py"]})
    on = sb.with_hardware({"ProgramArguments": ["/py", "/p/guardian_v1_armed.py"]})
    with pytest.raises(StageBError):
        sb.with_hardware(on)


# ---- dry run and refusals ------------------------------------------------------

def test_dry_run_changes_nothing_and_passes(tmp_path):
    system = FakeSystem(tmp_path)
    assert sb.switch(system.env(), apply=False) == 0
    assert not system.changed_anything()
    assert HARDWARE_FLAG not in system.v1_args()
    assert any("Dry run only" in line for line in system.output)


@pytest.mark.parametrize("kwargs,expected", [
    (dict(v06_protection="ARMED"), "not DISARMED"),
    (dict(v06_protection=None), "not DISARMED"),
    (dict(v1_armed=True), "v1.0 is ARMED"),
    (dict(hardware=True), "already"),
    (dict(with_record=False), "Commissioning record not found"),
])
def test_switch_refuses_when_unsafe_and_changes_nothing(tmp_path, kwargs, expected):
    system = FakeSystem(tmp_path, **kwargs)
    assert sb.switch(system.env(), apply=True) == 1
    assert any(expected in line for line in system.output), system.output
    assert not system.changed_anything()
    assert system.answers == [CONFIRM_PHRASE]          # never even asked


def test_switch_refuses_without_contact_with_v1(tmp_path):
    system = FakeSystem(tmp_path)
    system.v1_up = False
    assert sb.switch(system.env(), apply=True) == 1
    assert not system.changed_anything()


def test_wrong_confirmation_cancels_without_changes(tmp_path):
    system = FakeSystem(tmp_path)
    system.answers = ["yes"]
    assert sb.switch(system.env(), apply=True) == 1
    assert not system.changed_anything()
    assert HARDWARE_FLAG not in system.v1_args()


# ---- the real switch -------------------------------------------------------------

def test_switch_stops_v06_first_then_enables_v1_hardware(tmp_path):
    system = FakeSystem(tmp_path)
    assert sb.switch(system.env(), apply=True) == 0
    assert HARDWARE_FLAG in system.v1_args() and system.v1_args()[-1] == HARDWARE_TOKEN
    assert system.v1_hardware and not system.v1_armed        # never armed by the script
    assert not system.v06_alive and V06 in system.disabled and V06 not in system.loaded
    verbs = system.verbs()
    assert verbs.index("disable") < verbs.index("bootstrap")  # v0.6 gone before v1.0 restarts
    assert (tmp_path / "backups").exists() and list((tmp_path / "backups").iterdir())


def test_switch_works_when_v0_6_was_not_running(tmp_path):
    system = FakeSystem(tmp_path, v06_alive=False, v06_loaded=False, v06_disabled=True)
    assert sb.switch(system.env(), apply=True) == 0
    assert system.v1_hardware and not system.v06_alive


def test_failed_v1_restart_puts_everything_back(tmp_path):
    system = FakeSystem(tmp_path)
    original = (system.agents / f"{V1}.plist").read_bytes()
    system.v1_never_returns = True
    # v1.0 refuses to come up with hardware, then also cannot restart plain: restore must report it
    assert sb.switch(system.env(), apply=True) == 1
    assert any("FAILED" in line for line in system.output)
    assert (system.agents / f"{V1}.plist").read_bytes() == original


def test_hardware_launch_that_never_reports_restores_old_state(tmp_path):
    system = FakeSystem(tmp_path)
    original = (system.agents / f"{V1}.plist").read_bytes()
    real_run = system.run

    def run(cmd):
        rc, out = real_run(cmd)
        # first v1.0 start (the hardware one) fails to come up; the restore start succeeds
        if cmd[:2] == ["launchctl", "bootstrap"] and cmd[3].endswith(f"{V1}.plist") \
                and HARDWARE_FLAG in system.v1_args():
            system.v1_up = False
        return rc, out

    system.run = run
    env = system.env()
    env.run = run
    assert sb.switch(env, apply=True) == 1
    assert (system.agents / f"{V1}.plist").read_bytes() == original
    assert HARDWARE_FLAG not in system.v1_args()
    assert system.v06_alive and V06 not in system.disabled     # v0.6 restored as it was
    assert not system.v1_armed
    assert any("Restored" in line for line in system.output)


def test_v06_that_will_not_stop_aborts_before_touching_v1(tmp_path):
    system = FakeSystem(tmp_path)
    original = (system.agents / f"{V1}.plist").read_bytes()
    system.v06_wont_stop = True
    assert sb.switch(system.env(), apply=True) == 1
    assert (system.agents / f"{V1}.plist").read_bytes() == original
    assert HARDWARE_FLAG not in system.v1_args()
    assert V06 not in system.disabled                          # re-enabled


def test_bad_new_plist_is_never_installed(tmp_path):
    system = FakeSystem(tmp_path)
    original = (system.agents / f"{V1}.plist").read_bytes()
    system.lint_fails = True
    assert sb.switch(system.env(), apply=True) == 1
    assert (system.agents / f"{V1}.plist").read_bytes() == original
    assert not list(system.agents.glob("*.tmp"))


# ---- rollback ---------------------------------------------------------------------

def test_rollback_refuses_while_v1_is_armed(tmp_path):
    system = FakeSystem(tmp_path, hardware=True, v1_armed=True, v06_alive=False, v06_loaded=False, v06_disabled=True)
    assert sb.rollback(system.env(), apply=True) == 1
    assert not system.changed_anything()
    assert any("ARMED" in line for line in system.output)


def test_rollback_dry_run_changes_nothing(tmp_path):
    system = FakeSystem(tmp_path, hardware=True, v06_alive=False, v06_loaded=False, v06_disabled=True)
    assert sb.rollback(system.env(), apply=False) == 0
    assert not system.changed_anything()


def test_rollback_restores_v06_and_disables_v1_hardware(tmp_path):
    system = FakeSystem(tmp_path, hardware=True, v06_alive=False, v06_loaded=False, v06_disabled=True)
    assert sb.rollback(system.env(), apply=True) == 0
    assert HARDWARE_FLAG not in system.v1_args()
    assert not system.v1_hardware and not system.v1_armed
    assert system.v06_alive and system.v06_protection == "DISARMED"
    assert V06 not in system.disabled and V06 in system.loaded


def test_rollback_when_already_watching_only_still_restores_v06(tmp_path):
    system = FakeSystem(tmp_path, hardware=False, v06_alive=False, v06_loaded=False, v06_disabled=True)
    assert sb.rollback(system.env(), apply=True) == 0
    assert system.v06_alive


def test_switch_then_rollback_returns_to_the_original_v1_arguments(tmp_path):
    system = FakeSystem(tmp_path)
    before = system.v1_args()
    assert sb.switch(system.env(), apply=True) == 0
    assert sb.rollback(system.env(), apply=True) == 0
    assert system.v1_args() == before


# ---- status ------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs,expected", [
    (dict(v06_protection="ARMED"), "v0.6"),
    (dict(hardware=True, v1_armed=True, v06_alive=False), "v1.0"),
    (dict(hardware=True, v1_armed=True, v06_protection="ARMED"), "CONFLICT"),
    (dict(), "NONE"),
    (dict(hardware=False, v1_armed=True, v06_alive=False), "NONE"),   # watching only cannot cut
])
def test_status_names_who_protects(tmp_path, kwargs, expected):
    system = FakeSystem(tmp_path, **kwargs)
    lines, protected_by = sb.supervisor_report(system.env())
    assert protected_by == expected
    assert lines


def test_status_with_nothing_reachable(tmp_path):
    system = FakeSystem(tmp_path, v06_alive=False)
    system.v1_up = False
    assert sb.supervisor_report(system.env())[1] == "UNKNOWN"


def test_cli_entry_point_exists_and_status_runs(tmp_path):
    import subprocess
    done = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "guardian_stage_b.py"),
                           "status", "--operator-socket", str(tmp_path / "none.sock")],
                          capture_output=True, text=True, cwd=str(tmp_path), timeout=30)
    assert done.returncode == 0, done.stderr
    assert "PROTECTED_BY:" in done.stdout


# ---- the 2026-11-18 failure: bootstrap right after bootout failed with an I/O error ------------

def test_switch_survives_launchd_still_unloading_v1(tmp_path):
    system = FakeSystem(tmp_path)
    system.bootstrap_fail_times = 3
    system.linger_lists = 2
    assert sb.switch(system.env(), apply=True) == 0
    assert HARDWARE_FLAG in system.v1_args() and system.v1_hardware and not system.v1_armed


def test_a_bootstrap_that_never_works_still_restores_and_reports(tmp_path):
    system = FakeSystem(tmp_path)
    system.bootstrap_fail_times = 10 ** 6
    assert sb.switch(system.env(), apply=True) == 1
    assert any("FAILED" in line for line in system.output)
    assert HARDWARE_FLAG not in system.v1_args()


def test_rollback_loads_v1_when_the_file_is_already_watching_only_but_v1_is_not_running(tmp_path):
    system = FakeSystem(tmp_path, v06_alive=False, v06_loaded=False)
    system.loaded.discard(V1)
    system.v1_up = False
    assert sb.rollback(system.env(), apply=True) == 0
    assert system.v1_up and not system.v1_hardware and system.v06_alive
    assert V1 in system.loaded


def test_rollback_leaves_a_running_watching_only_v1_alone(tmp_path):
    system = FakeSystem(tmp_path, v06_alive=False, v06_loaded=False)
    assert sb.rollback(system.env(), apply=True) == 0
    assert not [c for c in system.calls if c[1] in ("bootout", "bootstrap") and V1 in " ".join(c)]


def test_the_rewritten_launchd_file_keeps_its_permissions(tmp_path):
    system = FakeSystem(tmp_path)
    path = system.agents / f"{V1}.plist"
    path.chmod(0o644)
    assert sb.switch(system.env(), apply=True) == 0
    assert oct(path.stat().st_mode & 0o777) == "0o644"


def test_bootstrap_waits_until_launchd_has_finished_unloading(tmp_path):
    system = FakeSystem(tmp_path)
    system.linger_lists = 8
    assert sb.switch(system.env(), apply=True) == 0
    assert system.bootstrap_errors == 0          # never asked launchd to load while it was still unloading


# ---- a Mac that never ran Guardian 0.6 (a new operator) -----------------------------------------

def _no_v06(tmp_path, **kw):
    return FakeSystem(tmp_path, v06_alive=False, v06_loaded=False, has_v06=False, **kw)


def _touches_v06(system):
    return [c for c in system.calls if any(V06 in str(part) for part in c)]


def test_switch_works_without_v06_and_never_touches_it(tmp_path):
    system = _no_v06(tmp_path)
    assert sb.switch(system.env(), apply=False) == 0
    assert not system.changed_anything()
    assert sb.switch(system.env(), apply=True) == 0
    assert HARDWARE_FLAG in system.v1_args() and system.v1_hardware and not system.v1_armed
    assert not [c for c in _touches_v06(system) if c[1] in ("bootout", "bootstrap", "enable", "disable")]
    assert any("nothing to stop" in line for line in system.output)
    assert not any("v0.6 is off" in line for line in system.output)


def test_a_failed_switch_without_v06_restores_v1_and_does_not_invent_v06(tmp_path):
    system = _no_v06(tmp_path)
    original = (system.agents / f"{V1}.plist").read_bytes()
    system.bootstrap_fail_times = sb.BOOTSTRAP_ATTEMPTS      # the hardware start fails; the restore works
    assert sb.switch(system.env(), apply=True) == 1
    assert (system.agents / f"{V1}.plist").read_bytes() == original
    assert not [c for c in _touches_v06(system) if c[1] in ("bootout", "bootstrap", "enable", "disable")]
    assert any("Restored: v1.0 is watching only" in line for line in system.output)


def test_a_v06_that_is_running_without_its_launchd_file_blocks_the_switch(tmp_path):
    system = FakeSystem(tmp_path, v06_alive=True, v06_loaded=False, has_v06=False)
    assert sb.switch(system.env(), apply=True) == 1
    assert not system.changed_anything()
    assert any("stop v0.6 yourself" in line for line in system.output)


def test_rollback_without_v06_returns_v1_to_watching_only_and_starts_nothing_else(tmp_path):
    system = _no_v06(tmp_path, hardware=True)
    system.v1_hardware = True
    assert sb.rollback(system.env(), apply=True) == 0
    assert HARDWARE_FLAG not in system.v1_args() and not system.v1_hardware
    assert not [c for c in _touches_v06(system) if c[1] in ("bootout", "bootstrap", "enable", "disable")]
    assert any("Nothing is protecting the rig" in line for line in system.output)


def test_with_v06_present_the_behaviour_is_unchanged(tmp_path):
    system = FakeSystem(tmp_path)
    assert sb.switch(system.env(), apply=True) == 0
    assert V06 in system.disabled and not system.v06_alive
    assert sb.rollback(system.env(), apply=True) == 0
    assert system.v06_alive


def test_rollback_refuses_when_v06_runs_without_its_launchd_file(tmp_path):
    system = FakeSystem(tmp_path, v06_alive=True, v06_loaded=False, has_v06=False)
    assert sb.rollback(system.env(), apply=True) == 1
    assert not system.changed_anything()
