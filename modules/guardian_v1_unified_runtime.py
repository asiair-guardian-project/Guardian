"""Single-owner, monitor-only Guardian runtime coordination.

This integrates an injected read-only observation runtime and operator IPC.
It deliberately does not construct real adapters, ARM, or enable hardware.
"""
from datetime import datetime, timezone
import logging
import time

from modules.guardian_v1_operator_socket import GuardianOperatorSocket


class GuardianV1UnifiedRuntime:
    def __init__(self, *, application, observation_runtime, socket_path,
                 interval_seconds=5.0, clock=None, sleep=None, logger=None, setup_provider=None):
        if interval_seconds <= 0:
            raise ValueError('interval_seconds must be positive')
        if application.mode.hardware_execution_enabled:
            raise RuntimeError('Unified runtime must start monitor-only')
        if application.recovery_store is None:
            raise ValueError('Durable recovery store required')
        self.application = application
        self.observation_runtime = observation_runtime
        self._last_observation = None
        self.socket = GuardianOperatorSocket(application, socket_path,
            observation_provider=lambda: self._last_observation,
            setup_provider=setup_provider)
        self.interval_seconds = interval_seconds
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.logger = logger or logging.getLogger('guardian_v1.unified')
        self.running = False

    def run(self, *, cycles=None):
        """Poll IPC and observation on one thread; never run as an armed session.

        An observation exception is recorded, not interpreted as safe. Fatal
        storage / programming failures propagate; socket is always closed.
        """
        if cycles is not None and cycles < 0:
            raise ValueError('cycles must be nonnegative')
        self.socket.start()
        self.running = True
        count = 0
        try:
            while self.running and (cycles is None or count < cycles):
                if self.application.mode.hardware_execution_enabled:
                    raise RuntimeError('Hardware mode changed during monitor-only run')
                start = self.clock()
                try:
                    cycle = self.observation_runtime.run_cycle(
                        armed=False, now=datetime.now(timezone.utc))
                    if cycle is None:
                        self._last_observation = None
                    else:
                        self._last_observation = {
                        "roof": cycle.observation.roof_state.name,
                        "controller": cycle.observation.asiair_state.name,
                        "mount_motion": cycle.observation.mount_motion.name,
                        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                except (OSError, TimeoutError, ConnectionError) as exc:
                    self._last_observation = None
                    self.logger.warning('Read-only observation unavailable: %s', exc)
                count += 1
                # IPC and observation share a thread: never mutate the
                # supervisor concurrently. Socket accept has a 250ms timeout.
                while self.running and self.clock() - start < self.interval_seconds:
                    self.socket.serve_once()
            return count
        finally:
            self.running = False
            self.socket.close()

    def stop(self):
        self.running = False
