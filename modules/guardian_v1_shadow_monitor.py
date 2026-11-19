"""Continuous, read-only Guardian 1.0 shadow monitoring."""

import logging
import time
from modules.alpaca_safety_monitor import AlpacaSafetyMonitorError
from modules.guardian_types import Capability, CapabilityStatus
from datetime import datetime, timezone


class GuardianV1ShadowMonitor:
    def __init__(self, *, runtime, application, interval_seconds=5):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        if application.mode.hardware_execution_enabled:
            raise RuntimeError("Shadow monitor requires hardware execution disabled")

        self.runtime = runtime
        self.application = application
        self.interval_seconds = interval_seconds
        self.logger = logging.getLogger("guardian_v1.shadow")

    def run(self, *, armed=False, cycles=None):
        cycle = 0

        self.logger.info("Guardian 1.0 shadow monitoring started")

        try:
            while cycles is None or cycle < cycles:
                if self.application.mode.hardware_execution_enabled:
                    raise RuntimeError(
                        "Hardware execution enabled during shadow monitoring"
                    )

                now = datetime.now(timezone.utc)
                try:
                    result = self.runtime.run_cycle(
                        armed=armed,
                        now=now,
                    )

                    observation = result.observation
                    evaluation = result.evaluation

                    roof_filter = result.roof_filter
                    capability_registry = getattr(
                        self.application, "capabilities", None
                    )
                    alpaca_status = (
                        capability_registry.status(
                            Capability.OBSERVATORY_SAFETY_MONITORING
                        ).name
                        if capability_registry is not None
                        else CapabilityStatus.UNKNOWN.name
                    )
                    kasa_status = (
                        capability_registry.status(
                            Capability.SAFETY_POWER_CONTROL
                        ).name
                        if capability_registry is not None
                        else CapabilityStatus.UNKNOWN.name
                    )
                    self.logger.info(
                        "roof_observed=%s roof_effective=%s "
                        "unknown_count=%d unknown_seconds=%.1f "
                        "unknown_timeout=%s alpaca_capability=%s "
                        "kasa_capability=%s "
                        "asiair=%s wave=%s session=%s incident=%s",
                        observation.roof_state.name,
                        roof_filter.effective_state.name,
                        roof_filter.consecutive_unknown,
                        roof_filter.unknown_seconds,
                        roof_filter.timed_out,
                        alpaca_status,
                        kasa_status,
                        observation.asiair_state.name,
                        observation.mount_motion.name,
                        evaluation.session.state.name,
                        evaluation.incident,
                    )

                except (OSError, TimeoutError, ConnectionError, AlpacaSafetyMonitorError) as exc:
                    self.logger.warning(
                        "Shadow observation failed: %s",
                        exc,
                    )

                cycle += 1

                if cycles is None or cycle < cycles:
                    time.sleep(self.interval_seconds)

        except KeyboardInterrupt:
            self.logger.info("Shadow monitoring stopped by operator")

        return cycle
