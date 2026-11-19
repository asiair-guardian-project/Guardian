"""Single-owner Guardian ARM gate runner.

Opt-in runner; does not alter the deployed monitor-only service. ARM is
deliberately not exposed over IPC until commissioning and operator command
authorization have been validated.
"""
from datetime import datetime, timezone
import logging
import time

from modules.guardian_v1_operator_socket import GuardianOperatorSocket


class GuardianV1GatedOwner:
    def __init__(self, *, gate, socket_path, interval_seconds=5.0,
                 clock=None, sleep=None, logger=None):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if gate.armed:
            raise RuntimeError("Owner must start DISARMED")
        if gate.application.mode.hardware_execution_enabled:
            raise RuntimeError("Owner must start monitor-only")
        self.gate = gate
        self.socket = GuardianOperatorSocket(gate.application, socket_path, gate=gate)
        self.interval_seconds = interval_seconds
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.logger = logger or logging.getLogger("guardian_v1.gated_owner")
        self.running = False

    def run(self, *, cycles=None):
        if cycles is not None and cycles < 0:
            raise ValueError("cycles must be nonnegative")
        self.socket.start()
        self.running = True
        count = 0
        try:
            while self.running and (cycles is None or count < cycles):
                start = self.clock()
                try:
                    self.gate.cycle(now=datetime.now(timezone.utc))
                except Exception as exc:
                    if self.gate.application.supervisor.incident is not None:
                        # Keep the owner alive to retry unresolved real shutdowns.
                        self.logger.exception("Incident active; retry on next cycle: %s", exc)
                    elif isinstance(exc, (OSError, TimeoutError, ConnectionError)):
                        self.logger.warning("Observation unavailable: %s", exc)
                    else:
                        raise
                count += 1
                while self.running and self.clock() - start < self.interval_seconds:
                    self.socket.serve_once()
            return count
        finally:
            self.running = False
            self.socket.close()

    def stop(self):
        self.running = False
