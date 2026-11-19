from types import SimpleNamespace
import pytest
from modules.guardian_v1_activation_interlock import (
    inspect_monitor_stopped, advisory_activation_lock, ActivationInterlockError)


def runner(output, code=0):
    return lambda *a, **k: SimpleNamespace(stdout=output, returncode=code)


def test_stopped_still_not_authorized():
    result = inspect_monitor_stopped(uid=501, runner=runner("state = not running\n"))
    assert result["launchagent_stopped"] is True
    assert result["activation_authorized"] is False


@pytest.mark.parametrize("output", [
    "state = running\\npid = 123\\n",
    "state = not running\\npid = 123\\n",
    "state = waiting\\n",
    "pid = 123\\n",
    "",
])
def test_unsafe_states_rejected(output):
    with pytest.raises(ActivationInterlockError):
        inspect_monitor_stopped(uid=501, runner=runner(output))


def test_missing_service_rejected():
    with pytest.raises(ActivationInterlockError):
        inspect_monitor_stopped(uid=501, runner=runner("", 113))


def test_lock_exclusive(tmp_path):
    path = tmp_path / "activation.lock"
    with advisory_activation_lock(path):
        with pytest.raises(ActivationInterlockError):
            with advisory_activation_lock(path):
                pass
    with advisory_activation_lock(path):
        pass


def test_lock_symlink_rejected(tmp_path):
    target = tmp_path / "target"
    target.write_text("x")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ActivationInterlockError):
        with advisory_activation_lock(link):
            pass
