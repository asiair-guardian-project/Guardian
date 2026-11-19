"""Read-only macOS monitor-stop preflight and advisory activation lock.

No activation operation is exposed. LaunchAgent absence is not sufficient proof
of exclusive ownership; a rogue/manual process or auto-restart remains possible.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import subprocess


class ActivationInterlockError(RuntimeError):
    pass


LABEL = "org.guardian.v1.monitor"


def inspect_monitor_stopped(*, uid: int | None = None,
                            label: str = LABEL,
                            runner=subprocess.run) -> dict:
    """Fail closed unless launchctl explicitly reports a stopped service.

    A missing/unloaded service is NOT accepted, because it does not establish
    that another monitor process isn't running.
    """
    uid = os.getuid() if uid is None else uid
    if not isinstance(uid, int) or uid < 0 or label != LABEL:
        raise ActivationInterlockError("Invalid monitor identity")
    try:
        result = runner(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ActivationInterlockError("Cannot verify monitor state") from exc
    if result.returncode != 0:
        raise ActivationInterlockError("Monitor state unavailable")
    states = re.findall(r"^\s*state = ([^\n]+)", result.stdout, re.MULTILINE)
    pids = re.findall(r"^\s*pid = (\d+)\s*$", result.stdout, re.MULTILINE)
    if not states or states[0].strip() != "not running" or pids:
        raise ActivationInterlockError("Monitor not verified stopped")
    # This check alone is not sufficient for activation.
    return {"launchagent_stopped": True, "activation_authorized": False,
            "commissioning_authorized": False, "hardware_commands": 0}


@contextmanager
def advisory_activation_lock(path: str | Path):
    """Exclusive nonblocking file lock; only coordinates cooperating clients.

    Lock does NOT stop Guardian and must never be treated as sufficient
    authorization for replacing the installation YAML.
    """
    path = Path(path)
    if path.is_symlink():
        raise ActivationInterlockError("Lock path is a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if not os.path.isfile(path):
            raise ActivationInterlockError("Invalid lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ActivationInterlockError("Another activation owns the lock") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
