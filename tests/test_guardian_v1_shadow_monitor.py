import logging
from types import SimpleNamespace

import pytest

from modules.guardian_v1_shadow_monitor import GuardianV1ShadowMonitor


class FakeRuntime:
    def __init__(self):
        self.calls = 0

    def run_cycle(self, *, armed, now):
        self.calls += 1
        return SimpleNamespace(
            roof_filter=SimpleNamespace(
                effective_state=SimpleNamespace(name="OPEN"),
                consecutive_unknown=0,
                unknown_seconds=0.0,
                timed_out=False,
            ),
            observation=SimpleNamespace(
                roof_state=SimpleNamespace(name="OPEN"),
                asiair_state=SimpleNamespace(name="ONLINE"),
                mount_motion=SimpleNamespace(name="MOVING"),
            ),
            evaluation=SimpleNamespace(
                session=SimpleNamespace(
                    state=SimpleNamespace(name="IMAGING_PERMITTED")
                ),
                incident=None,
            ),
        )


def test_shadow_monitor_runs_multiple_cycles(caplog):
    app = SimpleNamespace(
        mode=SimpleNamespace(hardware_execution_enabled=False)
    )
    runtime = FakeRuntime()
    monitor = GuardianV1ShadowMonitor(
        runtime=runtime,
        application=app,
        interval_seconds=0.001,
    )

    with caplog.at_level(logging.INFO, logger="guardian_v1.shadow"):
        count = monitor.run(armed=True, cycles=3)

    assert count == 3
    assert runtime.calls == 3
    assert "roof_observed=OPEN roof_effective=OPEN" in caplog.text


def test_shadow_monitor_rejects_hardware_enabled_mode():
    app = SimpleNamespace(
        mode=SimpleNamespace(hardware_execution_enabled=True)
    )

    with pytest.raises(RuntimeError, match="hardware execution disabled"):
        GuardianV1ShadowMonitor(
            runtime=FakeRuntime(),
            application=app,
        )


def test_shadow_monitor_stops_if_hardware_mode_changes():
    mode = SimpleNamespace(hardware_execution_enabled=False)
    app = SimpleNamespace(mode=mode)

    class ModeChangingRuntime(FakeRuntime):
        def run_cycle(self, *, armed, now):
            result = super().run_cycle(armed=armed, now=now)
            mode.hardware_execution_enabled = True
            return result

    runtime = ModeChangingRuntime()
    monitor = GuardianV1ShadowMonitor(
        runtime=runtime,
        application=app,
        interval_seconds=0.001,
    )

    with pytest.raises(RuntimeError, match="Hardware execution enabled"):
        monitor.run(armed=True, cycles=3)

    assert runtime.calls == 1


def test_shadow_monitor_logs_failure_and_continues(caplog):
    app = SimpleNamespace(
        mode=SimpleNamespace(hardware_execution_enabled=False)
    )

    class IntermittentRuntime(FakeRuntime):
        def run_cycle(self, *, armed, now):
            if self.calls == 0:
                self.calls += 1
                raise TimeoutError("ASIAIR observation timed out")
            return super().run_cycle(armed=armed, now=now)

    runtime = IntermittentRuntime()
    monitor = GuardianV1ShadowMonitor(
        runtime=runtime,
        application=app,
        interval_seconds=0.001,
    )

    with caplog.at_level(logging.INFO, logger="guardian_v1.shadow"):
        count = monitor.run(armed=True, cycles=3)

    assert count == 3
    assert runtime.calls == 3
    assert "ASIAIR observation timed out" in caplog.text
    assert "roof_observed=OPEN roof_effective=OPEN" in caplog.text


def test_shadow_monitor_writes_persistent_log(tmp_path):
    from logging.handlers import RotatingFileHandler

    log_path = tmp_path / "guardian_v1_shadow.log"

    logger = logging.getLogger("guardian_v1.shadow")
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
    )

    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    try:
        app = SimpleNamespace(
            mode=SimpleNamespace(hardware_execution_enabled=False)
        )

        monitor = GuardianV1ShadowMonitor(
            runtime=FakeRuntime(),
            application=app,
            interval_seconds=0.001,
        )

        assert monitor.run(armed=True, cycles=2) == 2

    finally:
        logger.removeHandler(handler)
        handler.close()

    contents = log_path.read_text()

    assert "Guardian 1.0 shadow monitoring started" in contents
    assert "roof_observed=OPEN roof_effective=OPEN" in contents
    assert "IMAGING_PERMITTED" in contents
