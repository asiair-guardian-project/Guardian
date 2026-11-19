import os
import pytest
from modules.guardian_v1_runtime_lock import (
    monitor_lifetime_lock, offline_activation_lock, GuardianRuntimeLockError,
)


def test_monitor_blocks_activation(tmp_path):
    lock = tmp_path / "runtime.lock"
    with monitor_lifetime_lock(lock):
        with pytest.raises(GuardianRuntimeLockError):
            with offline_activation_lock(lock):
                pass


def test_activation_blocks_monitor(tmp_path):
    lock = tmp_path / "runtime.lock"
    with offline_activation_lock(lock):
        with pytest.raises(GuardianRuntimeLockError):
            with monitor_lifetime_lock(lock):
                pass


def test_two_monitors_can_share(tmp_path):
    lock = tmp_path / "runtime.lock"
    with monitor_lifetime_lock(lock):
        with monitor_lifetime_lock(lock):
            pass


def test_release_allows_activation(tmp_path):
    lock = tmp_path / "runtime.lock"
    with monitor_lifetime_lock(lock):
        pass
    with offline_activation_lock(lock):
        pass


def test_symlink_rejected(tmp_path):
    target = tmp_path / "target"
    target.write_text("data")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(GuardianRuntimeLockError):
        with monitor_lifetime_lock(link):
            pass


def test_broad_permissions_rejected(tmp_path):
    lock = tmp_path / "runtime.lock"
    lock.write_text("")
    lock.chmod(0o644)
    with pytest.raises(GuardianRuntimeLockError):
        with offline_activation_lock(lock):
            pass


def test_lock_permissions_private(tmp_path):
    lock = tmp_path / "runtime.lock"
    with monitor_lifetime_lock(lock):
        assert os.stat(lock).st_mode & 0o777 == 0o600
