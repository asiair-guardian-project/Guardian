from types import SimpleNamespace
import pytest
from modules.guardian_v1_unified_runtime import GuardianV1UnifiedRuntime

class FakeSocket:
    def __init__(self): self.started = False; self.closed = False; self.polls = 0
    def start(self): self.started = True
    def serve_once(self): self.polls += 1
    def close(self): self.closed = True

class FakeRuntime:
    def __init__(self, fail=False): self.calls = []; self.fail = fail
    def run_cycle(self, *, armed, now):
        self.calls.append(armed)
        if self.fail: raise ConnectionError('offline')

def make_app(enabled=False, store=object()):
    return SimpleNamespace(mode=SimpleNamespace(hardware_execution_enabled=enabled), recovery_store=store)

def test_requires_monitor_only_and_store():
    with pytest.raises(RuntimeError): GuardianV1UnifiedRuntime(application=make_app(True), observation_runtime=FakeRuntime(), socket_path='/tmp/test')
    with pytest.raises(ValueError): GuardianV1UnifiedRuntime(application=make_app(store=None), observation_runtime=FakeRuntime(), socket_path='/tmp/test')

def test_single_owner_unarmed_cycles():
    runtime = FakeRuntime()
    ticks = iter([0, 2, 2, 4, 4, 6])
    runner = GuardianV1UnifiedRuntime(application=make_app(), observation_runtime=runtime,
                                      socket_path='/tmp/test', interval_seconds=1, clock=lambda: next(ticks))
    runner.socket = FakeSocket()
    assert runner.run(cycles=2) == 2
    assert runtime.calls == [False, False]
    assert runner.socket.started and runner.socket.closed

def test_observation_connection_failure_does_not_claim_safe():
    runtime = FakeRuntime(fail=True)
    ticks = iter([0, 2])
    runner = GuardianV1UnifiedRuntime(application=make_app(), observation_runtime=runtime,
                                      socket_path='/tmp/test', interval_seconds=1, clock=lambda: next(ticks))
    runner.socket = FakeSocket()
    assert runner.run(cycles=1) == 1
    assert runner.socket.closed

def test_mode_flip_fails_closed_and_closes_socket():
    app = make_app()
    runtime = FakeRuntime()
    ticks = iter([0, 2, 2])
    runner = GuardianV1UnifiedRuntime(application=app, observation_runtime=runtime,
                                      socket_path='/tmp/test', interval_seconds=1, clock=lambda: next(ticks))
    runner.socket = FakeSocket()
    class Flip:
        def run_cycle(self, *, armed, now): app.mode.hardware_execution_enabled = True
    runner.observation_runtime = Flip()
    with pytest.raises(RuntimeError): runner.run(cycles=2)
    assert runner.socket.closed
