"""A relaunched monitor must start after a hard kill left its socket behind.

Socket paths are short (/tmp/...) on purpose: macOS limits unix socket paths
to 104 characters and pytest's default temp folder on a Mac is longer.
No network, no hardware.
"""
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from modules.guardian_types import Capability
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_operator_socket import GuardianOperatorSocket

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


@pytest.fixture
def sockdir():
    directory = tempfile.mkdtemp(prefix="gs", dir="/tmp")  # mode 0700, ours
    yield Path(directory)
    shutil.rmtree(directory, ignore_errors=True)


def make_server(path):
    app = GuardianV1Application(configured_capabilities=set())
    return GuardianOperatorSocket(app, path)


def leave_stale_socket(path):
    """A socket file with no process behind it, as after a hard kill."""
    leftover = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    leftover.bind(str(path))
    leftover.close()  # closing does not remove the file
    assert path.exists()


def test_starts_when_a_stale_socket_is_left_behind(sockdir):
    path = sockdir / "operator.sock"
    leave_stale_socket(path)

    server = make_server(path)
    server.start()
    try:
        assert path.exists()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(str(path))  # the new server is the one answering
        client.close()
    finally:
        server.close()
    assert not path.exists()  # clean stop still removes it


def test_refuses_when_another_guardian_is_listening(sockdir):
    path = sockdir / "operator.sock"
    first = make_server(path)
    first.start()
    try:
        with pytest.raises(FileExistsError, match="already listening"):
            make_server(path).start()
        assert path.exists()  # the live one was not disturbed
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(str(path))
        client.close()
    finally:
        first.close()


def test_refuses_to_remove_a_regular_file(sockdir):
    path = sockdir / "operator.sock"
    path.write_text("precious")
    with pytest.raises(FileExistsError, match="not a Guardian socket"):
        make_server(path).start()
    assert path.read_text() == "precious"


def test_refuses_a_symlink_and_leaves_both_ends_alone(sockdir):
    target = sockdir / "target.txt"
    target.write_text("keep me")
    path = sockdir / "operator.sock"
    path.symlink_to(target)
    with pytest.raises(FileExistsError, match="symlink"):
        make_server(path).start()
    assert path.is_symlink()
    assert target.read_text() == "keep me"


def test_refuses_a_symlink_that_points_at_a_stale_socket(sockdir):
    real = sockdir / "real.sock"
    leave_stale_socket(real)
    path = sockdir / "operator.sock"
    path.symlink_to(real)
    with pytest.raises(FileExistsError, match="symlink"):
        make_server(path).start()
    assert real.exists() and path.is_symlink()


def test_insecure_directory_is_still_rejected(sockdir):
    sockdir.chmod(0o755)
    with pytest.raises(PermissionError):
        make_server(sockdir / "operator.sock").start()


def test_real_kill_minus_9_then_relaunch_starts_cleanly(sockdir):
    """The actual scenario: a Guardian process is SIGKILLed, then relaunched."""
    path = sockdir / "operator.sock"
    child_code = (
        "import sys, time\n"
        f"sys.path.insert(0, {PROJECT_ROOT!r})\n"
        "from modules.guardian_v1_application import GuardianV1Application\n"
        "from modules.guardian_v1_operator_socket import GuardianOperatorSocket\n"
        "app = GuardianV1Application(configured_capabilities=set())\n"
        f"s = GuardianOperatorSocket(app, {str(path)!r})\n"
        "s.start()\n"
        "print('READY', flush=True)\n"
        "time.sleep(60)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", child_code],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "READY"
        assert path.exists()
        os.kill(child.pid, signal.SIGKILL)  # no cleanup gets to run
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()

    assert path.exists()  # the hard kill really did leave it behind
    with pytest.raises(OSError):  # and nothing is listening on it
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1)
        try:
            probe.connect(str(path))
        finally:
            probe.close()

    relaunched = make_server(path)
    relaunched.start()  # before this patch: FileExistsError, forever
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(str(path))
        client.close()
    finally:
        relaunched.close()
