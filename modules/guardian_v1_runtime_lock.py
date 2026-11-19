"""Cooperative lifetime lock for Guardian monitor and offline activation.

The lock is advisory. It is only an effective interlock when *all* monitor
entrypoints and activation writers acquire the same inode for their lifetime.
This module does not modify or authorize any active configuration.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat


class GuardianRuntimeLockError(RuntimeError):
    pass


def _open_lock(path):
    path = Path(path)
    if path.is_symlink():
        raise GuardianRuntimeLockError("Lock symlink forbidden")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise GuardianRuntimeLockError("Cannot open runtime lock") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise GuardianRuntimeLockError("Lock must be a regular file")
        if st.st_uid != os.getuid():
            raise GuardianRuntimeLockError("Lock ownership mismatch")
        if st.st_mode & 0o077:
            raise GuardianRuntimeLockError("Lock permissions too broad")
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def monitor_lifetime_lock(path):
    """Hold shared lock for entire monitor lifetime, including socket cleanup."""
    fd = _open_lock(path)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GuardianRuntimeLockError("Activation holds exclusive lock") from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextmanager
def offline_activation_lock(path):
    """Require exclusive lock, refusing to proceed if any monitor holds shared."""
    fd = _open_lock(path)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GuardianRuntimeLockError("Monitor or another activation holds lock") from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
