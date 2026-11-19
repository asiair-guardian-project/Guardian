"""Armed-capable Guardian 1.0 runtime: one thread, one owner.

Differences from the watch-only GuardianV1UnifiedRuntime:
  * every cycle runs through the ARM gate (GuardianV1ArmedGate.cycle), so a
    session that has been ARMed is actually protected;
  * the operator socket is given the gate, so ARM / DISARM work;
  * hardware execution is enabled ONLY when the caller passes
    enable_hardware_execution=True, which the launcher does only for an
    explicit command-line setting. Without it this behaves as watch-only:
    the gate refuses ARM because hardware is off.

ARM itself still needs valid commissioning and a deliberate operator action;
none of that is bypassed here. An optional abort alerter is called after
every cycle.
"""
from datetime import datetime, timezone
import logging
import threading
import time

from modules.guardian_v1_event_journal import RigEventObserver
from modules.guardian_v1_operator_socket import GuardianOperatorSocket


class GuardianV1ArmedRuntime:
    def __init__(self, *, application, gate, observation_runtime, socket_path,
                 interval_seconds=5.0, enable_hardware_execution=False,
                 clock=None, sleep=None, logger=None, setup_provider=None,
                 alerter=None, journal=None):
        if interval_seconds <= 0:
            raise ValueError('interval_seconds must be positive')
        if application.recovery_store is None:
            raise ValueError('Durable recovery store required')
        if gate.application is not application:
            raise ValueError('ARM gate must belong to this application')
        if application.mode.hardware_execution_enabled:
            raise RuntimeError('Armed runtime must be constructed with hardware disabled')
        self.application = application
        self.gate = gate
        self.observation_runtime = observation_runtime
        self.enable_hardware_execution = bool(enable_hardware_execution)
        self.alerter = alerter
        self._observer = RigEventObserver(journal) if journal is not None else None
        self._last_observation = None
        self.socket = GuardianOperatorSocket(
            application, socket_path, gate=gate,
            observation_provider=lambda: self._last_observation,
            setup_provider=setup_provider)
        self.interval_seconds = interval_seconds
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.logger = logger or logging.getLogger('guardian_v1.armed')
        self.running = False
        # A stop requested at ANY time, even before run() has finished
        # starting, must not be lost (e.g. SIGTERM during startup).
        self._stop_requested = threading.Event()
        self.cycle_errors = 0

    def run(self, *, cycles=None):
        """Run cycles until stopped. The socket is always closed on exit.

        A failed cycle is logged and counted, never treated as safe and never
        allowed to end the loop: the gate has already disarmed itself, and an
        open incident keeps retrying its power-off on later cycles.
        """
        if cycles is not None and cycles < 0:
            raise ValueError('cycles must be nonnegative')
        self.socket.start()
        self.running = not self._stop_requested.is_set()
        if self.enable_hardware_execution and self.running:
            self.application.mode.enable_hardware_execution()
            self.logger.warning('Hardware execution ENABLED by launch setting; ARM still required')
        if self._observer is not None:
            self._observer.started(hardware_requested=self.enable_hardware_execution)
        count = 0
        try:
            while not self._stop_requested.is_set() and (cycles is None or count < cycles):
                start = self.clock()
                observation = None
                failure = None
                try:
                    cycle = self.gate.cycle(now=datetime.now(timezone.utc))
                    observation = cycle.observation
                    self._last_observation = {
                        "roof": cycle.observation.roof_state.name,
                        "controller": cycle.observation.asiair_state.name,
                        "mount_motion": cycle.observation.mount_motion.name,
                        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                except (OSError, TimeoutError, ConnectionError) as exc:
                    self._last_observation = None
                    self.logger.warning('Observation unavailable: %s', exc)
                    failure = f'Observation unavailable: {exc}'
                except Exception:
                    self._last_observation = None
                    self.cycle_errors += 1
                    self.logger.exception('Cycle failed; ARM revoked, retries continue')
                    failure = 'Cycle failed; ARM revoked, protection retries continue'
                if self._observer is not None:
                    self._observer.observe(
                        application=self.application, gate=self.gate,
                        observation=observation, failure=failure)
                self._notify_alerter()
                count += 1
                # IPC and cycles share one thread: never mutate the
                # supervisor concurrently. Socket accept has a 250 ms timeout.
                while not self._stop_requested.is_set() and self.clock() - start < self.interval_seconds:
                    self.socket.serve_once()
            return count
        finally:
            self.running = False
            self.socket.close()
            if self._observer is not None:
                self._observer.journal.event(
                    'INFO', 'MONITOR', 'STOPPED', 'Guardian v1.0 monitor stopped.')

    def _notify_alerter(self):
        if self.alerter is None:
            return
        try:
            self.alerter.observe(self.application.supervisor.incident)
        except Exception:  # an alert problem must never stop protection
            self.logger.exception('Abort alerter failed')

    def stop(self):
        self._stop_requested.set()
        self.running = False
