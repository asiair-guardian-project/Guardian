"""Stage B: move live power-cut responsibility from Guardian v0.6 to Guardian 1.0, and back.

Nothing here runs unless the operator uses --apply, and the switch to 1.0 also needs
a typed confirmation phrase. Both directions change only launchd job settings; they
never ARM anything, never cut or restore power, and never touch Kasa outlet 1.

Rules enforced:
  * never touch a supervisor that is ARMED (a restart of an armed v1.0 cuts power);
  * only one supervisor may be able to cut power at a time;
  * a failed switch puts everything back the way it was.
"""

from __future__ import annotations

import copy
import os
import plistlib
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

V1_LABEL = "org.guardian.v1.monitor"
V06_LABEL = "com.guardian.observatory"
HARDWARE_FLAG = "--enable-hardware-execution"
HARDWARE_TOKEN = "YES_CUT_POWER"
CONFIRM_PHRASE = "CUT POWER"
ARMED_ENTRY_POINT = "guardian_v1_armed.py"
ARM_NEEDS = ("--commissioning-record", "--kasa-host", "--installation-config",
             "--recovery-file", "--operator-socket")
WAIT_SECONDS = 60.0


class StageBError(Exception):
    """A refusal or failure that the operator should read."""


@dataclass
class Environment:
    uid: int
    v1_plist: Path
    v06_plist: Path
    backup_dir: Path
    run: Callable[[List[str]], Tuple[int, str]]
    v1_status: Callable[[], Optional[dict]]
    v06_state: Callable[[], dict]  # {"alive": bool, "pid": int|None, "protection": str|None}
    say: Callable[[str], None]
    confirm: Callable[[str], str]
    sleep: Callable[[float], None]
    now: Callable[[], datetime]
    file_exists: Callable[[str], bool] = lambda p: os.path.exists(p)


# ----- plist handling --------------------------------------------------------

def read_plist(path) -> dict:
    try:
        with open(path, "rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ValueError) as exc:
        raise StageBError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("ProgramArguments"), list):
        raise StageBError(f"{path} has no ProgramArguments list")
    return data


def _args(plist) -> List[str]:
    return [str(a) for a in plist["ProgramArguments"]]


def check_monitor_plist(plist) -> None:
    if not any(Path(a).name == ARMED_ENTRY_POINT for a in _args(plist)):
        raise StageBError(
            f"The v1.0 monitor job does not run {ARMED_ENTRY_POINT}; refusing to edit it")


def hardware_enabled_in(plist) -> bool:
    args = _args(plist)
    return HARDWARE_FLAG in args


def with_hardware(plist) -> dict:
    check_monitor_plist(plist)
    if hardware_enabled_in(plist):
        raise StageBError("The v1.0 monitor job already has hardware execution enabled")
    updated = copy.deepcopy(plist)
    updated["ProgramArguments"] = _args(plist) + [HARDWARE_FLAG, HARDWARE_TOKEN]
    return updated


def without_hardware(plist) -> dict:
    check_monitor_plist(plist)
    args = _args(plist)
    kept, skip = [], False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg == HARDWARE_FLAG:
            skip = index + 1 < len(args) and args[index + 1] == HARDWARE_TOKEN
            continue
        kept.append(arg)
    updated = copy.deepcopy(plist)
    updated["ProgramArguments"] = kept
    return updated


def _value_after(args, flag):
    if flag in args:
        index = args.index(flag)
        if index + 1 < len(args):
            return args[index + 1]
    return None


def arm_ingredient_problems(plist, env) -> List[str]:
    args = _args(plist)
    problems = [f"The v1.0 monitor job has no {flag}; ARM would be refused"
                for flag in ARM_NEEDS if _value_after(args, flag) is None]
    record = _value_after(args, "--commissioning-record")
    if record and not env.file_exists(record):
        problems.append(f"Commissioning record not found: {record}; ARM would be refused")
    return problems


# ----- launchd helpers -------------------------------------------------------

def _domain(env) -> str:
    return f"gui/{env.uid}"


def is_loaded(env, label) -> bool:
    rc, out = env.run(["launchctl", "list"])
    if rc != 0:
        return False
    return any(line.split()[-1:] == [label] for line in out.splitlines() if line.strip())


def is_disabled(env, label) -> bool:
    rc, out = env.run(["launchctl", "print-disabled", _domain(env)])
    if rc != 0:
        return False
    return any(f'"{label}" => disabled' in line for line in out.splitlines())


def _launchctl(env, *args, ignore_failure=False):
    rc, out = env.run(["launchctl", *args])
    if rc != 0 and not ignore_failure:
        raise StageBError(f"launchctl {' '.join(args)} failed: {out.strip() or rc}")
    return rc


def _wait(env, condition, what, seconds=WAIT_SECONDS):
    waited = 0.0
    while waited <= seconds:
        if condition():
            return
        env.sleep(1.0)
        waited += 1.0
    raise StageBError(f"Timed out waiting for {what}")


def _install_plist(env, plist, destination):
    """Write a plist next to its destination, lint it, then swap it in."""
    destination = Path(destination)
    handle, temp_name = tempfile.mkstemp(dir=str(destination.parent), suffix=".tmp")
    os.close(handle)
    try:
        with open(temp_name, "wb") as out:
            plistlib.dump(plist, out)
        if destination.exists():                       # keep the file's existing permissions
            os.chmod(temp_name, stat.S_IMODE(os.stat(destination).st_mode))
        rc, out_text = env.run(["plutil", "-lint", temp_name])
        if rc != 0:
            raise StageBError(f"New launchd file failed plutil -lint: {out_text.strip()}")
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _v1_is(env, hardware: bool) -> bool:
    status = env.v1_status()
    return bool(status and status.get("connected", True)
                and bool(status.get("hardware_execution_enabled")) == hardware
                and status.get("armed") is not True)


BOOTSTRAP_ATTEMPTS = 6
BOOTSTRAP_PAUSE_SECONDS = 3.0


def _bootstrap_with_retries(env, plist_path):
    """launchd unloads asynchronously: a bootstrap right after a bootout can fail with 'Input/output error'
    (seen on the real Mac, 2026-11-18). Wait, then retry a few times before giving up."""
    last = None
    for attempt in range(BOOTSTRAP_ATTEMPTS):
        if attempt:
            env.sleep(BOOTSTRAP_PAUSE_SECONDS)
        try:
            _launchctl(env, "bootstrap", _domain(env), str(plist_path))
            return
        except StageBError as exc:
            last = exc
            if is_loaded(env, V1_LABEL):       # it did load after all
                return
    raise last


def _reload_v1(env, plist_path):
    if is_loaded(env, V1_LABEL):
        _launchctl(env, "bootout", f"{_domain(env)}/{V1_LABEL}")
        _wait(env, lambda: not is_loaded(env, V1_LABEL), "launchd to finish unloading v1.0")
        env.sleep(BOOTSTRAP_PAUSE_SECONDS)
    _bootstrap_with_retries(env, plist_path)


def _restore_v06(env, was_loaded, was_disabled):
    """Put the v0.6 launchd job back exactly as the switch found it."""
    if was_disabled:
        _launchctl(env, "disable", f"{_domain(env)}/{V06_LABEL}")
        return
    if was_loaded:
        _start_v06(env)
    else:
        _launchctl(env, "enable", f"{_domain(env)}/{V06_LABEL}")


def _start_v06(env):
    _launchctl(env, "enable", f"{_domain(env)}/{V06_LABEL}")
    if not is_loaded(env, V06_LABEL):
        _launchctl(env, "bootstrap", _domain(env), str(env.v06_plist))

    def up():
        state = env.v06_state()
        return bool(state.get("alive")) and state.get("protection") == "DISARMED"

    _wait(env, up, "v0.6 to start DISARMED")


def _stop_v06(env):
    if is_loaded(env, V06_LABEL):
        _launchctl(env, "bootout", f"{_domain(env)}/{V06_LABEL}")
    _launchctl(env, "disable", f"{_domain(env)}/{V06_LABEL}")
    _wait(env, lambda: not env.v06_state().get("alive"), "v0.6 to stop")


# ----- status ----------------------------------------------------------------

def supervisor_report(env):
    """Return (lines, protected_by). protected_by: v0.6, v1.0, NONE, CONFLICT, UNKNOWN."""
    v06 = env.v06_state()
    v1 = env.v1_status()
    lines = []

    if v06.get("alive"):
        lines.append(f"v0.6:  running (PID {v06.get('pid')}), protection {v06.get('protection') or 'UNKNOWN'}")
    else:
        lines.append("v0.6:  not running")

    v06_armed = bool(v06.get("alive")) and v06.get("protection") == "ARMED"
    v1_hw = v1_armed = None

    if v1 and v1.get("connected", True):
        v1_hw = bool(v1.get("hardware_execution_enabled"))
        v1_armed = v1.get("armed") is True
        lines.append("v1.0:  running, " + ("can CUT POWER" if v1_hw else "watching only (cannot cut)")
                     + (", ARMED" if v1_armed else ", disarmed"))
    else:
        lines.append("v1.0:  no contact with the monitor")

    v1_cutting = bool(v1_hw and v1_armed)
    if v06_armed and v1_cutting:
        return lines, "CONFLICT"
    if v1_cutting:
        return lines, "v1.0"
    if v06_armed:
        return lines, "v0.6"
    if v1 is None and not v06.get("alive"):
        return lines, "UNKNOWN"
    return lines, "NONE"


# ----- switch ----------------------------------------------------------------

def has_v06(env) -> bool:
    """A Mac that never ran Guardian 0.6 (a new operator) has no v0.6 launchd file; Stage B then leaves v0.6 alone."""
    return Path(env.v06_plist).exists()


def switch_problems(env) -> List[str]:
    problems = []
    try:
        plist = read_plist(env.v1_plist)
        check_monitor_plist(plist)
        if hardware_enabled_in(plist):
            problems.append("The v1.0 monitor job already has hardware execution enabled (already Stage B?)")
        problems += arm_ingredient_problems(plist, env)
    except StageBError as exc:
        problems.append(str(exc))

    v06 = env.v06_state()
    if not has_v06(env) and v06.get("alive"):
        problems.append(f"v0.6 is running but its launchd file was not found ({env.v06_plist}); "
                        "stop v0.6 yourself first")
    if v06.get("alive") and v06.get("protection") != "DISARMED":
        problems.append(f"v0.6 is running with protection '{v06.get('protection') or 'UNKNOWN'}', not DISARMED; "
                        "DISARM it in Guardian Control first")

    v1 = env.v1_status()
    if not v1 or not v1.get("connected", True):
        problems.append("No contact with the v1.0 monitor; it must be running (watching only) before the switch")
    else:
        if v1.get("armed") is True:
            problems.append("v1.0 is ARMED; DISARM it first (restarting an armed v1.0 would cut power)")
        if v1.get("hardware_execution_enabled"):
            problems.append("v1.0 already reports hardware execution enabled")
    return problems


def switch(env, apply: bool) -> int:
    say = env.say
    say("=== Stage B SWITCH: Guardian 1.0 becomes the supervisor that can cut power ===")
    problems = switch_problems(env)

    say("Plan:")
    say("  1. back up the v1.0 launchd file")
    if has_v06(env):
        say("  2. stop v0.6 and disable it in launchd (so it cannot restart)")
    else:
        say("  2. (no Guardian 0.6 on this Mac: nothing to stop)")
    say(f"  3. add '{HARDWARE_FLAG} ...' to the v1.0 launchd file and restart v1.0 (it stays DISARMED)")
    say("  4. wait until v1.0 reports it can cut power and is still disarmed")
    say("  You then ARM v1.0 yourself. This script never arms and never switches power.")

    if problems:
        say("")
        say("REFUSED. Nothing was changed:")
        for problem in problems:
            say(f"  - {problem}")
        return 1

    if not apply:
        say("")
        say("Dry run only: nothing was changed. All checks passed.")
        say("To do it for real:  .venv/bin/python guardian_stage_b.py switch --apply")
        return 0

    say("")
    say("This lets Guardian 1.0 CUT POWER to the ASIAIR, mount and Pegasus when the roof")
    say("closes or the ASIAIR is lost, once you ARM it." + (" v0.6 will be switched off." if has_v06(env) else ""))
    answer = env.confirm(f"Type {CONFIRM_PHRASE} to continue, anything else cancels: ")
    if answer.strip() != CONFIRM_PHRASE:
        say("Cancelled. Nothing was changed.")
        return 1

    plist = read_plist(env.v1_plist)
    new_plist = with_hardware(plist)
    stamp = env.now().strftime("%Y%m%d-%H%M%S")
    env.backup_dir.mkdir(parents=True, exist_ok=True)
    backup = env.backup_dir / f"{V1_LABEL}.plist.pre-stage-b.{stamp}"
    shutil.copyfile(env.v1_plist, backup)
    say(f"Backed up: {backup}")

    v06_present = has_v06(env)
    v06_was_loaded = v06_present and is_loaded(env, V06_LABEL)
    v06_was_disabled = v06_present and is_disabled(env, V06_LABEL)

    plist_replaced = False

    try:
        if v06_present:
            _stop_v06(env)
            say("v0.6 stopped and disabled.")
        _install_plist(env, new_plist, env.v1_plist)
        plist_replaced = True
        _reload_v1(env, env.v1_plist)
        _wait(env, lambda: _v1_is(env, True), "v1.0 to restart with hardware execution enabled and disarmed")
    except StageBError as exc:
        say(f"FAILED: {exc}")
        say("Putting everything back the way it was ...")
        try:
            if plist_replaced:
                shutil.copyfile(backup, env.v1_plist)
                _reload_v1(env, env.v1_plist)
                _wait(env, lambda: _v1_is(env, False), "v1.0 to restart watching only")
            if v06_present:
                _restore_v06(env, v06_was_loaded, v06_was_disabled)
                say("Restored: v1.0 is watching only and v0.6 is back as it was.")
                say("Nothing is protecting the rig until you ARM v0.6 in Guardian Control.")
            else:
                say("Restored: v1.0 is watching only. Nothing is protecting the rig.")
        except StageBError as inner:
            say(f"RESTORE ALSO FAILED: {inner}")
            say("Run:  .venv/bin/python guardian_stage_b.py status    and then    guardian_stage_b.py rollback --apply")
        return 1

    say("")
    say("DONE. Guardian 1.0 can now cut power and is DISARMED." + (" v0.6 is off." if v06_present else ""))
    say("NEXT: open the Guardian 1.0 app and ARM it, then run:  .venv/bin/python guardian_stage_b.py status")
    say("To go back at any time:  DISARM v1.0, then  .venv/bin/python guardian_stage_b.py rollback --apply")
    return 0


# ----- rollback --------------------------------------------------------------

def rollback_problems(env) -> List[str]:
    problems = []
    v1 = env.v1_status()
    if v1 and v1.get("connected", True) and v1.get("armed") is True:
        problems.append("v1.0 is ARMED; DISARM it in its app first (restarting an armed v1.0 would cut power)")
    if not has_v06(env) and env.v06_state().get("alive"):
        problems.append(f"v0.6 is running but its launchd file was not found ({env.v06_plist}); stop v0.6 yourself first")
    try:
        plist = read_plist(env.v1_plist)
        check_monitor_plist(plist)
    except StageBError as exc:
        problems.append(str(exc))
    return problems


def rollback(env, apply: bool) -> int:
    say = env.say
    say("=== Stage B ROLLBACK: v0.6 becomes the supervisor again, v1.0 goes back to watching only ===")
    problems = rollback_problems(env)

    say("Plan:")
    say("  1. remove the hardware option from the v1.0 launchd file and restart v1.0 (watching only)")
    if has_v06(env):
        say("  2. enable v0.6 in launchd and start it (it comes up DISARMED)")
        say("  You then ARM v0.6 in Guardian Control. This script never arms.")
    else:
        say("  2. (no Guardian 0.6 on this Mac: nothing to start)")
        say("  Nothing will be protecting the rig until you decide what to do next. This script never arms.")

    if problems:
        say("")
        say("REFUSED. Nothing was changed:")
        for problem in problems:
            say(f"  - {problem}")
        return 1

    if not apply:
        say("")
        say("Dry run only: nothing was changed. All checks passed.")
        say("To do it for real:  .venv/bin/python guardian_stage_b.py rollback --apply")
        return 0

    plist = read_plist(env.v1_plist)
    stamp = env.now().strftime("%Y%m%d-%H%M%S")
    env.backup_dir.mkdir(parents=True, exist_ok=True)
    backup = env.backup_dir / f"{V1_LABEL}.plist.pre-rollback.{stamp}"
    shutil.copyfile(env.v1_plist, backup)

    try:
        if hardware_enabled_in(plist):
            _install_plist(env, without_hardware(plist), env.v1_plist)
            _reload_v1(env, env.v1_plist)
            _wait(env, lambda: _v1_is(env, False), "v1.0 to restart watching only")
            say("v1.0 is watching only.")
        else:
            say("v1.0's launchd file was already watching only.")
            if not _v1_is(env, False):
                say("v1.0 is not running; loading it (watching only) ...")
                _reload_v1(env, env.v1_plist)
                _wait(env, lambda: _v1_is(env, False), "v1.0 to start watching only")
                say("v1.0 is watching only.")
        if has_v06(env):
            _start_v06(env)
    except StageBError as exc:
        say(f"FAILED: {exc}")
        say("Check:  .venv/bin/python guardian_stage_b.py status")
        return 1

    say("")
    if has_v06(env):
        say("DONE. v0.6 is running DISARMED and v1.0 is watching only.")
        say("NEXT: ARM v0.6 in Guardian Control once the roof reads OPEN, then run imaging_check.sh.")
    else:
        say("DONE. v1.0 is watching only (it cannot cut power). Nothing is protecting the rig.")
    return 0


# ----- CLI environment -------------------------------------------------------

def real_environment(project_root, socket_path, launch_agents=None, uid=None) -> Environment:
    import json
    import subprocess
    import time

    from modules.guardian_v1_start_guard import ask_status

    project_root = Path(project_root)
    agents = Path(launch_agents) if launch_agents else Path.home() / "Library" / "LaunchAgents"

    def run(cmd):
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)
        return done.returncode, (done.stdout or "") + (done.stderr or "")

    def v1_status():
        try:
            reply = ask_status(socket_path, 2.0)
        except Exception:
            return None
        if not reply or reply.get("code") != "STATUS":
            return None
        return {"connected": True, "armed": reply.get("armed"),
                "hardware_execution_enabled": reply.get("hardware_execution_enabled"),
                "session": reply.get("session")}

    def v06_state():
        try:
            data = json.loads((project_root / "guardian_status.json").read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
        except (OSError, ValueError, TypeError):
            return {"alive": False, "pid": None, "protection": None}
        alive = False
        if pid > 0 and data.get("running") is True:
            try:
                os.kill(pid, 0)
                alive = True
            except ProcessLookupError:
                alive = False
            except PermissionError:
                alive = True
        return {"alive": alive, "pid": pid or None, "protection": data.get("protection")}

    return Environment(
        uid=uid if uid is not None else os.getuid(),
        v1_plist=agents / f"{V1_LABEL}.plist",
        v06_plist=agents / f"{V06_LABEL}.plist",
        backup_dir=project_root / "launchd" / "backups",
        run=run, v1_status=v1_status, v06_state=v06_state,
        say=lambda text: print(text, flush=True),
        confirm=input, sleep=time.sleep, now=datetime.now,
    )
