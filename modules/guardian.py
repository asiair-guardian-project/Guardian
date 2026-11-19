import asyncio
import os
import platform
import socket
import subprocess
import sys
import time


from modules import logger
from modules.asiair_monitor import asiair_available
from modules.alpaca_safety_monitor import (
    AlpacaSafetyMonitorError,
    read_alpaca_safety_status,
)
from modules.config_loader import load_config
from modules.event_engine import EventEngine
from modules.network_monitor import internet_available
from modules.notification import NotificationEngine
from modules.protection_engine import ProtectionEngine
from modules.roof_monitor import RoofStatusError, read_roof_status
from modules.roof_freshness import (
    roof_status_age_seconds,
    roof_status_is_stale,
)
from modules.session_manager import SessionManager
from modules.emergency_state_store import EmergencyStateStore
from modules.state_tracker import StateTracker
from modules.ups_monitor import UPSStatusError, read_ups_status
from modules.wave_monitor import WaveMonitorError, read_wave_status
from modules.control_interface import (
    ControlCommandError,
    clear_control_command,
    read_control_command,
)
from modules.status_writer import StatusWriteError, write_status
from modules.wave_stop_controller import (
    WaveStopError,
    stop_wave_safely,
)
from modules.wave_network import (
    ensure_wave_connection,
    get_wave_network_diagnostics,
)
from modules.kasa_controller import (
    KasaController,
    KasaControllerError,
    KasaSafetyError,
)
from modules.alert_manager import (
    AlertManager,
    AlertManagerError,
)
from modules.wave_position_sampler import (
    WavePositionSamplerError,
    sample_positions,
    wave_is_moving,
)
class Guardian:
    """Coordinates Guardian subsystems."""

    def __init__(self):
        self.config = load_config()

        self.version = self.config["guardian"]["version"]

        self.notifier = NotificationEngine(
            enabled=self.config["notifications"]["enabled"],
            minimum_level=self.config["notifications"]["minimum_level"],
            pushover_enabled=self.config["notifications"].get(
                "pushover_enabled",
                False,
            ),
        )

        self.events = EventEngine(self.notifier)
        self.protection = ProtectionEngine()
        self.alert_manager = AlertManager(
            self.config["control"]["alert_file"]
        )
        self.emergency_state_store = EmergencyStateStore(
            self.config["control"]["emergency_state_file"]
        )

        self.session = SessionManager(
            observatory_name=self.config["system"]["name"],
            guardian_version=self.version,
        )

        self.network_state = StateTracker()
        self.asiair_state = StateTracker()
        self.asiair_seen_online_this_session = False
        self.wave_seen_online_this_session = False
        self.roof_state = StateTracker()
        self.roof_freshness_state = StateTracker()
        self.ups_state = StateTracker()
        self.wave_state = StateTracker()
        self.wave_status = None
        self.wave_stop_status = "NOT_REQUESTED"
        self.protection_results = {}
        self.roof_close_protection_triggered = False

        self.emergency_retry_active = False
        self.emergency_started_at = None
        self.emergency_last_attempt_at = None
        self.emergency_last_wave_stop_attempt_at = None
        self.emergency_source = None
        self.emergency_event_type = None
        self.emergency_operator_acknowledged = False

    def restore_emergency_state(self):
        """
        Restore durable emergency state without executing hardware actions.

        Returns False if the record is missing, invalid, or unreadable.
        Such failures must block ARM.
        """
        from modules.emergency_state_store import EmergencyStateError

        self.emergency_state_ready = False
        self.emergency_state_error = None

        try:
            record = self.emergency_state_store.read()
        except EmergencyStateError as error:
            self.emergency_state_error = str(error)
            logger.critical(
                "EMERGENCY_STATE | RECOVERY_FAILED | "
                f"{error}. ARM must remain blocked."
            )
            return False

        state = record["session_state"]

        if state in ("EMERGENCY_IN_PROGRESS", "ABORTED"):
            if not self.session.restore_emergency_abort():
                self.emergency_state_error = (
                    "Cannot restore emergency over an active session."
                )
                return False

            self.emergency_operator_acknowledged = record[
                "operator_acknowledged"
            ]
            self.protection_results = dict(
                record["protection_results"]
            )
            self.emergency_source = record["abort_reason"]
            self.emergency_event_type = None

        # Restored retries are historical information, not authorization
        # to execute additional hardware shutdown commands.
        self.emergency_retry_active = False
        self.emergency_started_at = None
        self.emergency_last_attempt_at = None
        self.emergency_last_wave_stop_attempt_at = None

        self.emergency_state_ready = True

        logger.info(
            "EMERGENCY_STATE | RECOVERED | "
            f"Persisted state={state}; "
            f"Session state={self.session.state}; "
            f"Operator acknowledged="
            f"{self.emergency_operator_acknowledged}"
        )
        return True

    def record_emergency_abort(self):
        """
        Persist the terminal emergency-aborted session state.

        Preserve the original incident cause and operator acknowledgment.
        Storage failure blocks future ARM but must not stop protection.
        """
        from modules.emergency_state_store import EmergencyStateError

        try:
            existing = self.emergency_state_store.read()

            if existing["session_state"] not in (
                "EMERGENCY_IN_PROGRESS",
                "ABORTED",
            ):
                raise EmergencyStateError(
                    "Cannot record emergency abort without "
                    "an existing emergency."
                )

            record = dict(existing)
            record["session_state"] = "ABORTED"
            record["protection_results"] = dict(self.protection_results)

            self.emergency_state_store.write(record)

            if self.emergency_state_store.read() != record:
                raise EmergencyStateError(
                    "Emergency-abort verification failed."
                )

        except EmergencyStateError as error:
            self.emergency_state_ready = False
            self.emergency_state_error = str(error)
            logger.critical(
                "EMERGENCY_STATE | ABORT_SAVE_FAILED | "
                f"{error}. ARM blocked; protection must continue."
            )
            return False

        return True

    def update_emergency_results(self):
        """
        Persist current shutdown results without replacing the incident.

        Never reactivate retries after operator acknowledgment.
        Storage failure blocks future ARM but not emergency protection.
        """
        from modules.emergency_state_store import EmergencyStateError

        try:
            existing = self.emergency_state_store.read()

            if existing["session_state"] != "ABORTED":
                raise EmergencyStateError(
                    "Cannot update results without an ABORTED record."
                )

            if existing["operator_acknowledged"]:
                raise EmergencyStateError(
                    "Cannot update an acknowledged emergency."
                )

            updated = dict(existing)
            updated["protection_results"] = dict(
                self.protection_results
            )
            updated["emergency_retry_active"] = bool(
                self.emergency_retry_active
            )

            self.emergency_state_store.write(updated)

            if self.emergency_state_store.read() != updated:
                raise EmergencyStateError(
                    "Emergency-result verification failed."
                )

        except EmergencyStateError as error:
            self.emergency_state_ready = False
            self.emergency_state_error = str(error)
            logger.critical(
                "EMERGENCY_STATE | RESULT_SAVE_FAILED | "
                f"{error}. ARM blocked; protection must continue."
            )
            return False

        return True

    def acknowledge_emergency_abort(self):
        """
        Explicit operator override of outstanding emergency retries.

        This does not verify shutdown, restore equipment power,
        or restart the aborted imaging session.
        """

        if self.session.state != self.session.ABORTED:
            logger.warning(
                "PROTECTION | ACK_ABORT_REJECTED | "
                "No aborted imaging session exists."
            )
            return False

        if self.emergency_operator_acknowledged:
            logger.info(
                "PROTECTION | ACK_ABORT_ALREADY_ACKNOWLEDGED | "
                "This aborted session was already acknowledged."
            )
            return False

        if not getattr(self, "emergency_state_ready", False):
            logger.critical(
                "PROTECTION | ACK_ABORT_REJECTED | "
                "Emergency-state recovery has not succeeded."
            )
            return False

        from modules.emergency_state_store import EmergencyStateError

        retries_were_active = self.emergency_retry_active

        try:
            record = self.emergency_state_store.read()

            if record["session_state"] != "ABORTED":
                raise EmergencyStateError(
                    "Persistent record is not ABORTED."
                )

            if record["operator_acknowledged"]:
                raise EmergencyStateError(
                    "Persistent emergency is already acknowledged."
                )

            updated = dict(record)
            updated["operator_acknowledged"] = True
            updated["emergency_retry_active"] = False

            self.emergency_state_store.write(updated)

            if self.emergency_state_store.read() != updated:
                raise EmergencyStateError(
                    "Acknowledgment verification failed."
                )

        except EmergencyStateError as error:
            self.emergency_state_ready = False
            self.emergency_state_error = str(error)
            logger.critical(
                "PROTECTION | ACK_ABORT_PERSISTENCE_FAILED | "
                f"{error}. ARM remains blocked."
            )
            return False

        self.emergency_retry_active = False
        self.emergency_operator_acknowledged = True

        logger.critical(
            "PROTECTION | EMERGENCY_OPERATOR_ACKNOWLEDGED | "
            f"Outstanding retries canceled={retries_were_active}. "
            "Acknowledgment does NOT verify equipment shutdown. "
            "Imaging session remains ABORTED."
        )

        return True

    def emergency_retry_interval_seconds(self):
        """Return the current Kasa retry interval for an active emergency."""

        if not self.emergency_retry_active:
            return None

        elapsed = time.monotonic() - self.emergency_started_at

        if elapsed < 120:
            return 15

        if elapsed < 720:
            return 60

        return 300

    def start_emergency_retry(self, source, event_type):
        """Begin or preserve persistent emergency protection retry state."""

        if (
            self.session.state == self.session.ABORTED
            and self.emergency_operator_acknowledged
        ):
            logger.warning(
                "PROTECTION | EMERGENCY_RETRY_BLOCKED | "
                "Operator has acknowledged this aborted session."
            )
            return

        now = time.monotonic()

        if not self.emergency_retry_active:
            self.emergency_operator_acknowledged = False
            self.emergency_retry_active = True
            self.emergency_started_at = now
            self.emergency_last_attempt_at = now
            self.emergency_last_wave_stop_attempt_at = now
            self.emergency_source = source
            self.emergency_event_type = event_type

    def emergency_retry_due(self):
        """Return True when another emergency protection attempt is due."""

        if not getattr(self, "emergency_retry_active", False):
            return False

        if self.emergency_last_attempt_at is None:
            return True

        interval = self.emergency_retry_interval_seconds()

        return (
            time.monotonic() - self.emergency_last_attempt_at
            >= interval
        )

    def emergency_wave_stop_retry_due(self):
        """Return True when another controlled Wave STOP attempt is due."""

        if not getattr(self, "emergency_retry_active", False):
            return False

        if getattr(self, "wave_stop_status", None) != "FAILED":
            return False

        last_attempt = getattr(
            self,
            "emergency_last_wave_stop_attempt_at",
            None,
        )

        if last_attempt is None:
            return True

        return time.monotonic() - last_attempt >= 15

    def process_emergency_retry(self):
        """Retry unresolved emergency Kasa shutdown when due."""

        if self.emergency_wave_stop_retry_due():
            self.emergency_last_wave_stop_attempt_at = time.monotonic()

            logger.critical(
                "PROTECTION | WAVE_STOP_RETRY | "
                "Retrying controlled Wave STOP."
            )

            self.execute_wave_stop()

        if not self.emergency_retry_due():
            return False

        self.emergency_last_attempt_at = time.monotonic()

        logger.critical(
            "PROTECTION | EMERGENCY_RETRY | "
            f"Source={self.emergency_source} "
            f"Event={self.emergency_event_type}"
        )

        targets = ["WAVE", "PEGASUS", "ASIAIR"]

        batch_result = self.execute_kasa_emergency_batch(targets)

        result_names = {
            "WAVE": ("POWER_OFF_WAVE", "Wave 150i"),
            "PEGASUS": ("POWER_OFF_PEGASUS", "Pegasus"),
            "ASIAIR": ("POWER_OFF_ASIAIR", "ASIAIR"),
        }

        if not batch_result:
            for target in targets:
                result_name, _ = result_names[target]
                self.protection_results[result_name] = "FAILED"

            return False

        verification = batch_result["verification"]

        for target in targets:
            result_name, alias = result_names[target]

            if verification.get(alias, {}).get("verified_off"):
                self.protection_results[result_name] = "VERIFIED"

                if target == "ASIAIR":
                    self.quit_asiair_app()
            else:
                self.protection_results[result_name] = "FAILED"

        all_verified = all(
            self.protection_results.get(result_name) == "VERIFIED"
            for result_name, _ in result_names.values()
        )

        if all_verified:
            self.emergency_retry_active = False
            self.emergency_started_at = None
            self.emergency_last_attempt_at = None
            self.emergency_last_wave_stop_attempt_at = None
            self.emergency_source = None
            self.emergency_event_type = None

            logger.critical(
                "PROTECTION | EMERGENCY_RETRY_COMPLETE | "
                "All emergency outlets verified OFF."
            )

        return all_verified

    def show_startup_operator_alert(self):
        """
        Show one macOS notification for an unresolved Guardian alert.

        No notification is shown when no active alert exists.
        """

        try:
            alert = self.alert_manager.read_alert()

        except AlertManagerError as error:
            logger.error(
                "ALERT | READ_FAILED | "
                f"Unable to read persistent alert: {error}"
            )
            return False

        if alert is None:
            return False

        source = alert.get("source", "UNKNOWN")
        event_type = alert.get("event_type", "UNKNOWN")
        results = alert.get("protection_results", {})

        result_text = ", ".join(
            f"{name}: {status}"
            for name, status in results.items()
        )

        incident_message = alert.get(
            "message",
            f"{source} {event_type}.",
        )

        message = (
            f"{incident_message} "
            f"Guardian actions: "
            f"{result_text or 'See Guardian log.'}"
        )

        shown = self.notifier.mac_notification(
            "Guardian Overnight Incident",
            message,
        )

        if shown:
            logger.info(
                "ALERT | STARTUP_NOTIFICATION_SHOWN | "
                "Unresolved incident shown in macOS Notification Center."
            )

        return shown

    def start(self):
        """Run one-time Guardian startup tasks."""

        logger.info("================================")
        logger.info(f"Guardian v{self.version} Started")
        logger.info(
            f"Observatory Name: {self.config['system']['name']}"
        )
        logger.info(f"Hostname: {socket.gethostname()}")
        logger.info(f"Operating System: {platform.platform()}")
        logger.info(f"Python Version: {sys.version}")
        logger.info(f"Session Active: {self.session.active}")

        self.notifier.info("Guardian startup complete.")

        self.show_startup_operator_alert()

        logger.info("================================")

    def roof_ready_for_rearm(self):
        """Require a fresh OPEN roof reading after an emergency abort."""

        roof_config = self.config["roof"]
        roof_source = roof_config.get("source", "file")

        try:
            if roof_source == "alpaca":
                result = read_alpaca_safety_status(
                    host=roof_config.get("alpaca_host"),
                    port=roof_config.get("alpaca_port", 443),
                    device_number=roof_config.get(
                        "alpaca_device_number"
                    ),
                    timeout_seconds=roof_config.get(
                        "alpaca_timeout_seconds", 5
                    ),
                )

                ready = result["status"] == "OPEN"

            elif roof_source == "file":
                result = read_roof_status(
                    roof_config["status_file"]
                )

                threshold = roof_config.get(
                    "stale_after_seconds"
                )

                ready = (
                    result["status"] == "OPEN"
                    and threshold is not None
                    and not roof_status_is_stale(
                        result["timestamp"],
                        threshold,
                    )
                )

            else:
                logger.warning(
                    "SESSION | REARM_ROOF_BLOCKED | "
                    f"Unsupported roof source: {roof_source}"
                )
                return False

        except (
            RoofStatusError,
            AlpacaSafetyMonitorError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            logger.warning(
                "SESSION | REARM_ROOF_BLOCKED | "
                f"Roof verification failed: {error}"
            )
            return False

        if not ready:
            logger.warning(
                "SESSION | REARM_ROOF_BLOCKED | "
                "Roof is not confirmed OPEN and FRESH."
            )

        return ready

    def start_session(self):
        """Start a protected imaging session."""

        if not getattr(self, "emergency_state_ready", False):
            logger.critical(
                "SESSION | ARM_BLOCKED | "
                "Emergency-state recovery has not succeeded. "
                f"Reason: {getattr(self, 'emergency_state_error', None) or 'Not initialized'}"
            )
            return False

        if self.emergency_retry_active:
            logger.warning(
                "SESSION | ARM_BLOCKED | "
                "Cannot arm while an unresolved emergency "
                "shutdown is still active."
            )
            return False

        if (
            self.session.state == self.session.ABORTED
            and not self.emergency_operator_acknowledged
        ):
            logger.warning(
                "SESSION | ARM_BLOCKED | "
                "Previous emergency abort requires explicit "
                "operator ACK_ABORT before a new session."
            )
            return False

        if (
            self.session.state == self.session.ABORTED
            and not self.roof_ready_for_rearm()
        ):
            logger.warning(
                "SESSION | ARM_BLOCKED | "
                "Post-abort ARM requires a fresh OPEN roof reading."
            )
            return False

        started = self.session.start()

        if started:
            # A new, explicitly armed session must never inherit
            # emergency retry state from an earlier incident.
            # Historical alerts and incident records are preserved.
            self.emergency_retry_active = False
            self.emergency_started_at = None
            self.emergency_last_attempt_at = None
            self.emergency_last_wave_stop_attempt_at = None
            self.emergency_source = None
            self.emergency_event_type = None
            self.emergency_operator_acknowledged = False

            self.roof_close_protection_triggered = False
            self.asiair_seen_online_this_session = False
            self.wave_seen_online_this_session = False
            self.events.emit(
                source="SESSION",
                event_type="STARTED",
                severity="INFO",
                message="Imaging session started. Protection rules are armed.",
            )
            self.wave_stop_status = "NOT_REQUESTED"
            self.protection_results = {}

        return started

    def stop_session(self):
        """Stop the protected imaging session."""

        stopped = self.session.stop()

        if stopped:
            self.roof_close_protection_triggered = False
            self.events.emit(
                source="SESSION",
                event_type="STOPPED",
                severity="INFO",
                message="Imaging session stopped. Protection rules are disarmed.",
            )

        return stopped

    def monitor_once(self):
        """Run one Guardian monitoring cycle."""

        # Operator control
        self.process_control_command()

        # Continue unresolved emergency protection even after the
        # imaging session has entered the terminal ABORTED state.
        self.process_emergency_retry()

        # An aborted session is terminal. Guardian remains running so the
        # operator can start a future session, but no further equipment
        # monitoring is performed for the aborted session.
        if self.session.state == self.session.ABORTED:
            self.publish_status()
            return

        # Internet
        test_url = self.config["network"]["internet_test_url"]
        timeout = self.config["network"]["timeout_seconds"]

        internet_ok = internet_available(test_url, timeout)

        if self.network_state.update(internet_ok):
            if internet_ok:
                self.events.emit(
                    source="NETWORK",
                    event_type="CONNECTED",
                    severity="INFO",
                    message="Internet connection is available.",
                )
            else:
                self.events.emit(
                    source="NETWORK",
                    event_type="OFFLINE",
                    severity="WARNING",
                    message="Internet connection is unavailable.",
                )

        # ASIAIR — Ethernet only
        asiair_host = self.config["asiair"]["ip_address"]
        asiair_timeout = self.config["asiair"]["timeout_seconds"]

        if not asiair_host:
            asiair_ok = False
            asiair_error = "No ASIAIR Ethernet IP is configured."
        else:
            asiair_ok = asiair_available(
                asiair_host,
                asiair_timeout,
            )
            asiair_error = None

        if self.session.active and asiair_ok:
            self.asiair_seen_online_this_session = True

        if self.asiair_state.update(asiair_ok):
            if asiair_ok:
        
                self.events.emit(
                    source="ASIAIR",
                    event_type="ONLINE",
                    severity="INFO",
                    message=(
                        f"ASIAIR Ethernet interface is reachable at "
                        f"{asiair_host}."
                    ),
                )

            else:
                if (
                    self.session.active
                    and not self.asiair_seen_online_this_session
                ):
                    logger.info(
                        "ASIAIR | STARTUP_OFFLINE | "
                        "ASIAIR is not yet online for this session."
                    )
                else:
                    self.events.emit(
                        source="ASIAIR",
                        event_type="OFFLINE",
                        severity="WARNING",
                        message=(
                            f"ASIAIR Ethernet unavailable: {asiair_error}"
                            if asiair_error
                            else "ASIAIR Ethernet interface is not responding."
                        ),
                    )

                if (
                    self.session.active
                    and self.asiair_seen_online_this_session
                ):
                    self.handle_asiair_offline()
        # Wave 150i
        try:
            wave_result = read_wave_status()
            wave_ok = True
            wave_error = None
            self.wave_status = wave_result

        except WaveMonitorError as error:
            wave_result = None
            wave_ok = False
            wave_error = str(error)
            self.wave_status = None

            if (
                self.session.active
                and self.wave_seen_online_this_session
                and self.wave_state.state is not False
            ):
                try:
                    diagnostics = get_wave_network_diagnostics()
                    logger.warning(
                        "WAVE | NETWORK_DIAGNOSTICS | "
                        f"en1_ip={diagnostics['en1_ip']} | "
                        f"route_interface={diagnostics['route_interface']} | "
                        f"ping_ok={diagnostics['ping_ok']}"
                    )

                except Exception as diagnostic_error:
                    logger.warning(
                        "WAVE | NETWORK_DIAGNOSTICS_ERROR | "
                        f"{diagnostic_error}"
                    )

                try:
                    recovery_result = ensure_wave_connection()

                except Exception as recovery_error:
                    logger.critical(
                        "WAVE | NETWORK_RECOVERY_ERROR | "
                        f"{recovery_error}"
                    )
                    recovery_result = "OFFLINE"

                if recovery_result in ("ONLINE", "RECOVERED"):
                    try:
                        wave_result = read_wave_status()

                    except WaveMonitorError as verify_error:
                        wave_error = str(verify_error)
                        recovery_result = "OFFLINE"

                    else:
                        wave_ok = True
                        wave_error = None
                        self.wave_status = wave_result

                        logger.action(
                            "WAVE | NETWORK_RECOVERED | "
                            "Wave communication was restored and verified."
                        )

                if recovery_result == "OFFLINE":
                    pass

            elif self.session.active:
                pass

        if self.session.active and wave_ok:
            self.wave_seen_online_this_session = True

        if self.wave_state.update(wave_ok):
            if wave_ok:
                self.events.emit(
                    source="WAVE",
                    event_type="ONLINE",
                    severity="INFO",
                    message=(
                        "Wave 150i is reachable. "
                        f"Axis 1 status {wave_result['axis1']['status']}, "
                        f"position {wave_result['axis1']['position']}. "
                        f"Axis 2 status {wave_result['axis2']['status']}, "
                        f"position {wave_result['axis2']['position']}."
                    ),
                )
            else:
                if (
                    self.session.active
                    and not self.wave_seen_online_this_session
                ):
                    logger.info(
                        "WAVE | STARTUP_OFFLINE | "
                        "Wave is not yet online for this session."
                    )
                else:
                    self.events.emit(
                        source="WAVE",
                        event_type="OFFLINE",
                        severity="WARNING",
                        message=(
                            f"Wave 150i is not responding: {wave_error}"
                        ),
                    )

        # Roof
        roof_config = self.config["roof"]
        roof_source = roof_config.get("source", "file")

        try:
            if roof_source == "alpaca":
                roof_result = read_alpaca_safety_status(
                    host=roof_config.get("alpaca_host"),
                    port=roof_config.get("alpaca_port", 443),
                    device_number=roof_config.get(
                        "alpaca_device_number"
                    ),
                    timeout_seconds=roof_config.get(
                        "alpaca_timeout_seconds",
                        5,
                    ),
                )
                roof_status = roof_result["status"]
                roof_timestamp = None

            else:
                roof_result = read_roof_status(
                    roof_config["status_file"]
                )
                roof_status = roof_result["status"]
                roof_timestamp = roof_result["timestamp"]

        except (RoofStatusError, AlpacaSafetyMonitorError) as error:
            roof_status = "UNKNOWN"
            roof_error = str(error)
            freshness_state = "UNKNOWN"
            roof_is_stale = None
            roof_age_seconds = None

        else:
            roof_error = None

            if roof_source == "alpaca":
                freshness_state = "FRESH"
                roof_is_stale = False
                roof_age_seconds = 0

            else:
                stale_after_seconds = roof_config.get(
                    "stale_after_seconds"
                )

                if stale_after_seconds is None:
                    freshness_state = "UNKNOWN"
                    roof_is_stale = None
                    roof_age_seconds = None

                else:
                    roof_age_seconds = roof_status_age_seconds(
                        roof_timestamp
                    )

                    roof_is_stale = roof_status_is_stale(
                        roof_timestamp,
                        stale_after_seconds,
                    )

                    freshness_state = (
                        "STALE"
                        if roof_is_stale
                        else "FRESH"
                    )

        # Roof status logging
        if self.roof_state.update(roof_status):
            if roof_status == "UNKNOWN":
                self.events.emit(
                    source="ROOF",
                    event_type="UNKNOWN",
                    severity="ERROR",
                    message=f"Unable to determine roof status: {roof_error}",
                )
            else:
                self.events.emit(
                    source="ROOF",
                    event_type=roof_status,
                    severity="INFO",
                    message=f"Roof status changed to {roof_status}.",
                )

        # Roof freshness logging
        if self.roof_freshness_state.update(freshness_state):
            if freshness_state == "STALE":
                self.events.emit(
                    source="ROOF",
                    event_type="STALE",
                    severity="WARNING",
                    message=(
                        f"Roof status data is stale. "
                        f"Age: {roof_age_seconds:.0f} seconds."
                    ),
                )

            elif freshness_state == "FRESH":
                self.events.emit(
                    source="ROOF",
                    event_type="FRESH",
                    severity="INFO",
                    message=(
                        f"Roof status data is fresh. "
                        f"Age: {roof_age_seconds:.0f} seconds."
                    ),
                )

        # Roof gate
        if self.session.state == self.session.WAITING_FOR_ROOF:
            if (
                roof_status == "OPEN"
                and freshness_state == "FRESH"
            ):
                if self.session.permit_imaging():
                    self.events.emit(
                        source="SESSION",
                        event_type="IMAGING_PERMITTED",
                        severity="INFO",
                        message=(
                            "Roof is OPEN and status data is FRESH. "
                            "Imaging is now permitted."
                        ),
                    )

        # Roof protection
        elif self.session.state == self.session.IMAGING_PERMITTED:
            if (
                roof_status == "CLOSED"
                and freshness_state == "FRESH"
                and not self.roof_close_protection_triggered
            ):
                self.roof_close_protection_triggered = True

                logger.info(
                    "ROOF | CLOSE_SAFETY_CHECK | "
                    "Roof closed. Verifying Wave motion before "
                    "selecting normal shutdown or emergency protection."
                )

                wave_moving = None

                try:
                    sample_result = sample_positions(
                        interval_seconds=5
                    )

                    wave_moving = wave_is_moving(
                        sample_result
                    )

                except WavePositionSamplerError as error:
                    logger.critical(
                        "ROOF | CLOSE_WAVE_MOTION_UNKNOWN | "
                        f"Unable to determine whether Wave is moving: {error}"
                    )

                if wave_moving is None:
                    self.evaluate_protection(
                        source="ROOF",
                        event_type="CLOSED_WAVE_MOTION_UNKNOWN",
                    )

                    if self.session.abort():
                        self.events.emit(
                            source="SESSION",
                            event_type="ABORTED",
                            severity="CRITICAL",
                            message=(
                                "Imaging session aborted because the roof "
                                "closed and Wave motion could not be determined. "
                                "Guardian executed fail-safe protection."
                            ),
                        )

                elif wave_moving:
                    logger.critical(
                        "ROOF | CLOSE_WAVE_MOVING | "
                        "Roof closed while Wave motion was detected. "
                        "Guardian executed emergency protection."
                    )

                    self.evaluate_protection(
                        source="ROOF",
                        event_type="CLOSED_WAVE_MOVING",
                    )

                    if self.session.abort():
                        self.events.emit(
                            source="SESSION",
                            event_type="ABORTED",
                            severity="CRITICAL",
                            message=(
                                "Imaging session aborted because the roof "
                                "closed while the Wave was moving. "
                                "Guardian executed emergency protection."
                            ),
                        )

                else:
                    logger.info(
                        "ROOF | NORMAL_CLOSE_WAVE_STATIONARY | "
                        "Roof closed and Wave motion was verified stopped. "
                        "Normal shutdown detected."
                    )

                    shutdown_ok = self.execute_kasa_normal_shutdown()

                    if shutdown_ok:
                        logger.info(
                            "ROOF | NORMAL_CLOSE_SHUTDOWN_COMPLETE | "
                            "Normal post-imaging power shutdown completed."
                        )
                    else:
                        logger.error(
                            "ROOF | NORMAL_CLOSE_SHUTDOWN_FAILED | "
                            "Normal post-imaging power shutdown did not "
                            "complete successfully."
                        )

                    self.stop_session()

        # UPS
        try:
            ups_status = read_ups_status()
            power_source = ups_status["power_source"]

        except UPSStatusError as error:
            power_source = "UNKNOWN"
            ups_error = str(error)
        else:
            ups_error = None

        if self.ups_state.update(power_source):
            if power_source == "AC":
                self.events.emit(
                    source="UPS",
                    event_type="AC_POWER",
                    severity="INFO",
                    message=(
                        f"Utility power available. "
                        f"UPS battery {ups_status['battery_percent']}%. "
                        f"State: {ups_status['state']}."
                    ),
                )

            elif power_source == "UPS":
                self.events.emit(
                    source="UPS",
                    event_type="ON_BATTERY",
                    severity="WARNING",
                    message=(
                        f"Utility power lost. "
                        f"UPS battery {ups_status['battery_percent']}%. "
                        f"Runtime: {ups_status['runtime']}."
                    ),
                )

            else:
                self.events.emit(
                    source="UPS",
                    event_type="UNKNOWN",
                    severity="ERROR",
                    message=f"Unable to determine UPS status: {ups_error}",
                )

        if power_source == "UPS" and ups_status["battery_percent"] <= 35 and self.session.active:
            self.events.emit(source="UPS", event_type="LOW_BATTERY", severity="CRITICAL", message=f"UPS battery has reached {ups_status['battery_percent']}%. Imaging shutdown required.")
            self.evaluate_protection(source="UPS", event_type="LOW_BATTERY")
            if self.session.abort():
                self.events.emit(
                    source="SESSION",
                    event_type="ABORTED",
                    severity="CRITICAL",
                    message=(
                        "Imaging session aborted because UPS battery "
                        "reached the emergency threshold. Shutdown "
                        "verification does not affect abort status."
                    ),
                )

        # Publish runtime status
        self.publish_status()
    def _run_kasa_power_action(self, label, action_factory):
        """
        Run one Kasa shutdown action with one retry for
        transient communication failures.

        Safety-validation failures are never retried.
        """

        for attempt in range(2):
            try:
                return action_factory()

            except KasaSafetyError as error:
                logger.critical(
                    f"{label} | POWER_OFF_SAFETY_FAILED | {error}"
                )
                return False

            except Exception as error:
                if attempt == 0:
                    logger.warning(
                        f"{label} | POWER_OFF_RETRY | "
                        f"Transient failure: {error}"
                    )
                    time.sleep(2)
                    continue

                logger.critical(
                    f"{label} | POWER_OFF_FAILED | {error}"
                )
                return False

        return False


    def execute_wave_stop(self):
        """
        Execute and verify a controlled STOP of both Wave axes.

        This is a real hardware action.
        """

        logger.action(
            "WAVE | STOP_REQUESTED | "
            "Executing controlled STOP on both axes."
        )

        try:
            result = stop_wave_safely()

        except WaveStopError as error:
            self.wave_stop_status = "FAILED"

            logger.critical(
                f"WAVE | STOP_FAILED | {error}"
            )
            return False

        self.wave_stop_status = "VERIFIED"

        logger.action(
            "WAVE | STOP_VERIFIED | "
            "Both axes verified stationary."
        )

        return result

    def execute_wave_power_off(self):
        """
        Execute and verify emergency power-off of the Wave 150i.

        This is a real hardware action and is intended only as
        a fallback when controlled Wave STOP cannot be verified.
        """

        logger.critical(
            "WAVE | POWER_OFF_REQUESTED | "
            "Controlled STOP failed. Requesting emergency power-off."
        )

        try:
            controller = KasaController(
                self.config["kasa"]["power_strip_ip"]
            )

            result = asyncio.run(
                controller.power_off_wave()
            )

        except KasaControllerError as error:
            logger.critical(
                f"WAVE | POWER_OFF_FAILED | {error}"
            )
            return False

        except Exception as error:
            logger.critical(
                f"WAVE | POWER_OFF_ERROR | {error}"
            )
            return False

        logger.critical(
            "WAVE | POWER_OFF_VERIFIED | "
            "Wave 150i power verified OFF."
        )

        return result

    def execute_pegasus_power_off(self):
        """
        Execute and verify emergency power-off of the Pegasus Powerbox.

        This is a real hardware action.
        """

        logger.critical(
            "PEGASUS | POWER_OFF_REQUESTED | "
            "Requesting emergency power-off."
        )

        try:
            controller = KasaController(
                self.config["kasa"]["power_strip_ip"]
            )

            result = asyncio.run(
                controller.power_off_pegasus()
            )

        except KasaControllerError as error:
            logger.critical(
                f"PEGASUS | POWER_OFF_FAILED | {error}"
            )
            return False

        except Exception as error:
            logger.critical(
                f"PEGASUS | POWER_OFF_ERROR | {error}"
            )
            return False

        logger.critical(
            "PEGASUS | POWER_OFF_VERIFIED | "
            "Pegasus power verified OFF."
        )

        return result

    def execute_asiair_power_off(self):
        """
        Execute and verify emergency power-off of the ASIAIR.

        Transient Kasa communication failures receive one retry.
        """

        logger.critical(
            "ASIAIR | POWER_OFF_REQUESTED | "
            "Requesting emergency power-off."
        )

        def power_action():
            controller = KasaController(
                self.config["kasa"]["power_strip_ip"]
            )

            return asyncio.run(
                controller.power_off_asiair()
            )

        result = self._run_kasa_power_action(
            "ASIAIR",
            power_action,
        )

        if not result:
            return False

        logger.critical(
            "ASIAIR | POWER_OFF_VERIFIED | "
            "ASIAIR power verified OFF."
        )

        return result

    def execute_kasa_normal_shutdown(self):
        """
        Power off the normal post-imaging Kasa outlets.

        This is housekeeping after imaging has ended and the Wave
        has already been verified stationary. It is not an emergency.
        """

        targets = [
            "ASIAIR",
            "WAVE",
            "PEGASUS",
        ]

        logger.info(
            "KASA | NORMAL_SHUTDOWN_REQUESTED | "
            "Powering off ASIAIR, Wave 150i, and Pegasus."
        )

        try:
            controller = KasaController(
                self.config["kasa"]["power_strip_ip"]
            )

            result = asyncio.run(
                controller.power_off_emergency_targets(
                    targets
                )
            )

        except KasaSafetyError as error:
            logger.error(
                "KASA | NORMAL_SHUTDOWN_SAFETY_FAILED | "
                f"{error}"
            )
            return False

        except Exception as error:
            logger.error(
                "KASA | NORMAL_SHUTDOWN_FAILED | "
                f"{error}"
            )
            return False

        verification = result.get(
            "verification",
            {}
        )

        expected_aliases = [
            "ASIAIR",
            "Wave 150i",
            "Pegasus",
        ]

        all_off = all(
            verification.get(alias, {}).get(
                "verified_off",
                False,
            )
            for alias in expected_aliases
        )

        if not all_off:
            logger.error(
                "KASA | NORMAL_SHUTDOWN_VERIFY_FAILED | "
                "One or more imaging outlets could not be "
                "verified OFF."
            )
            return False

        logger.info(
            "KASA | NORMAL_SHUTDOWN_COMPLETE | "
            "ASIAIR, Wave 150i, and Pegasus verified OFF."
        )

        self.quit_asiair_app()

        return True

    def execute_kasa_imaging_startup(self):
        """
        Power on the normal imaging equipment before an imaging session.

        Uses one HS300 command session followed by one fresh discovery
        for final verification. The Mac Mini is never a startup target.
        """

        logger.info(
            "KASA | IMAGING_STARTUP_REQUESTED | "
            "Powering on Pegasus, Wave 150i, and ASIAIR."
        )

        try:
            controller = KasaController(
                self.config["kasa"]["power_strip_ip"]
            )

            result = asyncio.run(
                controller.power_on_imaging_targets()
            )

        except KasaSafetyError as error:
            logger.error(
                "KASA | IMAGING_STARTUP_SAFETY_FAILED | "
                f"{error}"
            )
            return False

        except Exception as error:
            logger.error(
                "KASA | IMAGING_STARTUP_FAILED | "
                f"{error}"
            )
            return False

        verification = result.get(
            "verification",
            {}
        )

        expected_aliases = [
            "ASIAIR",
            "Wave 150i",
            "Pegasus",
        ]

        all_on = all(
            verification.get(alias, {}).get(
                "verified_on",
                False,
            )
            for alias in expected_aliases
        )

        if not all_on:
            logger.error(
                "KASA | IMAGING_STARTUP_VERIFY_FAILED | "
                "One or more imaging outlets could not be "
                "verified ON."
            )
            return False

        logger.info(
            "KASA | IMAGING_STARTUP_COMPLETE | "
            "ASIAIR, Wave 150i, and Pegasus verified ON."
        )

        return True

    def quit_asiair_app(self):
        """Gracefully quit the ASIAIR2 macOS application."""

        try:
            running = subprocess.run(
                ["pgrep", "-x", "ASIAIR2"],
                capture_output=True,
                text=True,
            )

            if running.returncode != 0:
                logger.info(
                    "ASIAIR | APP_ALREADY_CLOSED | "
                    "ASIAIR2 application is not running."
                )
                return True

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "ASIAIR2" to quit',
                ],
                check=True,
                timeout=10,
                capture_output=True,
                text=True,
            )

            logger.info(
                "ASIAIR | APP_QUIT | "
                "ASIAIR2 application quit successfully."
            )
            return True

        except Exception as error:
            logger.warning(
                "ASIAIR | APP_QUIT_FAILED | "
                f"Unable to quit ASIAIR2 application: {error}"
            )
            return False

    def execute_kasa_emergency_batch(self, targets):
        """
        Execute and verify a batch emergency Kasa shutdown.

        Uses one HS300 command session followed by one fresh
        discovery for final verification.
        """

        logger.critical(
            "KASA | EMERGENCY_BATCH_REQUESTED | "
            f"Targets: {targets}"
        )

        try:
            controller = KasaController(
                self.config["kasa"]["power_strip_ip"]
            )

            result = asyncio.run(
                controller.power_off_emergency_targets(
                    targets
                )
            )

        except KasaSafetyError as error:
            logger.critical(
                f"KASA | EMERGENCY_BATCH_SAFETY_FAILED | {error}"
            )
            return False

        except Exception as error:
            logger.critical(
                f"KASA | EMERGENCY_BATCH_FAILED | {error}"
            )
            return False

        logger.critical(
            "KASA | EMERGENCY_BATCH_COMPLETE | "
            f"Targets: {targets}"
        )

        return result

    def handle_asiair_offline(self):
        """
        Handle ASIAIR loss during an active protected session.

        If the Wave is moving, execute the ASIAIR-loss protection path.
        If the Wave is stationary, mark normal imaging shutdown.

        If Wave motion cannot be determined, fail safe and execute
        protection.
        """

        if not self.session.active:
            logger.info(
                "ASIAIR | OFFLINE_IDLE | "
                "ASIAIR unavailable while Guardian is not armed."
            )
            return False

        try:
            sample_result = sample_positions(
                interval_seconds=5
            )

            moving = wave_is_moving(sample_result)

        except WavePositionSamplerError as error:
            logger.critical(
                "ASIAIR | OFFLINE_WAVE_MOTION_UNKNOWN | "
                f"Unable to determine whether Wave is moving: {error}"
            )

            self.evaluate_protection(
                source="ASIAIR",
                event_type="OFFLINE",
            )

            if self.session.abort():
                self.events.emit(
                    source="SESSION",
                    event_type="ABORTED",
                    severity="CRITICAL",
                    message=(
                        "Imaging session aborted because the ASIAIR "
                        "became unavailable and Wave motion could not "
                        "be determined. Guardian executed fail-safe "
                        "protection."
                    ),
                )

            self.create_operator_alert(
                source="ASIAIR",
                event_type="OFFLINE_WAVE_MOTION_UNKNOWN",
                message=(
                    "ASIAIR became unavailable while Guardian "
                    "could not verify whether the Wave was moving. "
                    "Guardian executed fail-safe protection."
                ),
            )

            return True

        if moving:
            logger.critical(
                "ASIAIR | OFFLINE_WAVE_MOVING | "
                "ASIAIR unavailable and Wave motion detected."
            )

            self.evaluate_protection(
                source="ASIAIR",
                event_type="OFFLINE",
            )

            if self.session.abort():
                self.events.emit(
                    source="SESSION",
                    event_type="ABORTED",
                    severity="CRITICAL",
                    message=(
                        "Imaging session aborted because the ASIAIR "
                        "became unavailable while the Wave was moving. "
                        "Guardian executed emergency protection."
                    ),
                )

            self.create_operator_alert(
                source="ASIAIR",
                event_type="OFFLINE_WAVE_MOVING",
                message=(
                    "ASIAIR became unavailable while the Wave "
                    "was moving. Guardian executed protection."
                ),
            )

            return True


        logger.info(
            "ASIAIR | OFFLINE_WAVE_STATIONARY | "
            "ASIAIR unavailable but Wave is verified stationary. "
            "Normal imaging shutdown detected."
        )

        return False

    def record_emergency_start(self, source, event_type):
        """
        Persist an emergency before protective hardware actions begin.

        A storage failure must not prevent emergency protection, but
        must invalidate recovery readiness and block future ARM.
        """
        from modules.emergency_state_store import EmergencyStateError

        reason = f"{source}:{event_type}"

        record = {
            "schema_version": 1,
            "session_state": "EMERGENCY_IN_PROGRESS",
            "abort_reason": reason,
            "operator_acknowledged": False,
            "emergency_retry_active": True,
            "protection_results": {},
        }

        try:
            existing = self.emergency_state_store.read()

            if existing["session_state"] != "DISARMED":
                raise EmergencyStateError(
                    "Existing emergency record must be preserved: "
                    f"{existing['session_state']} "
                    f"({existing['abort_reason']})"
                )

            self.emergency_state_store.write(record)

            if self.emergency_state_store.read() != record:
                raise EmergencyStateError(
                    "Emergency-start verification failed."
                )
        except EmergencyStateError as error:
            self.emergency_state_ready = False
            self.emergency_state_error = str(error)
            logger.critical(
                "EMERGENCY_STATE | WRITE_FAILED | "
                f"{error}. ARM blocked; emergency protection "
                "must continue."
            )
            return False

        return True

    def evaluate_protection(self, source, event_type):
        """
        Evaluate protective actions.

        Controlled Wave STOP is attempted first. Required Kasa
        emergency power actions are grouped into one shared-session
        batch with one fresh verification discovery.
        Other actions remain simulation-only.
        """

        actions = self.protection.evaluate(
            source=source,
            event_type=event_type,
            session_active=self.session.active,
        )

        self.protection_results = {}

        kasa_targets = []

        for action in actions:
            if action == "STOP_WAVE":
                stop_result = self.execute_wave_stop()

                if stop_result:
                    self.protection_results[action] = "VERIFIED"
                    kasa_targets.append("WAVE")

                else:
                    self.protection_results[action] = "FAILED"
                    kasa_targets.append("WAVE")

            elif action == "POWER_OFF_PEGASUS":
                kasa_targets.append("PEGASUS")

            elif action == "POWER_OFF_ASIAIR":
                kasa_targets.append("ASIAIR")

                batch_result = self.execute_kasa_emergency_batch(
                    kasa_targets
                )

                if not batch_result:
                    for target in kasa_targets:
                        result_name = {
                            "WAVE": "POWER_OFF_WAVE",
                            "PEGASUS": "POWER_OFF_PEGASUS",
                            "ASIAIR": "POWER_OFF_ASIAIR",
                        }[target]

                        self.protection_results[
                            result_name
                        ] = "FAILED"

                else:
                    verification = batch_result["verification"]

                    target_results = {
                        "WAVE": (
                            "POWER_OFF_WAVE",
                            "Wave 150i",
                        ),
                        "PEGASUS": (
                            "POWER_OFF_PEGASUS",
                            "Pegasus",
                        ),
                        "ASIAIR": (
                            "POWER_OFF_ASIAIR",
                            "ASIAIR",
                        ),
                    }

                    for target in kasa_targets:
                        result_name, alias = target_results[target]

                        target_verification = verification.get(
                            alias,
                            {},
                        )

                        if target_verification.get(
                            "verified_off"
                        ):
                            self.protection_results[
                                result_name
                            ] = "VERIFIED"

                            if target == "ASIAIR":
                                self.quit_asiair_app()

                        else:
                            self.protection_results[
                                result_name
                            ] = "FAILED"

            else:
                logger.action(
                    f"SIMULATION | {action} | "
                    "No hardware action executed."
                )
                self.protection_results[action] = "SIMULATED"

        required_power_results = (
            "POWER_OFF_WAVE",
            "POWER_OFF_PEGASUS",
            "POWER_OFF_ASIAIR",
        )

        if any(
            result in self.protection_results
            for result in required_power_results
        ):
            all_power_verified = all(
                self.protection_results.get(result) == "VERIFIED"
                for result in required_power_results
            )

            if not all_power_verified:
                self.start_emergency_retry(source, event_type)

        return actions

    def publish_status(self):
        """Publish the current Guardian runtime status."""

        status_file = self.config["control"]["status_file"]

        status_data = {
            "guardian_version": self.version,
            "running": True,
            "session_active": self.session.active,
            "session_state": self.session.state,
            "imaging_permitted": self.session.imaging_permitted,
            "protection": (
                "ARMED"
                if self.session.active
                else "DISARMED"
            ),
            "pid": os.getpid(),
            "wave": self.wave_status,
            "wave_stop_status": self.wave_stop_status,
            "emergency_retry_active": self.emergency_retry_active,
            "emergency_operator_acknowledged": (
                self.emergency_operator_acknowledged
            ),
            "emergency_power_shutdown_verified": all(
                self.protection_results.get(action) == "VERIFIED"
                for action in (
                    "POWER_OFF_WAVE",
                    "POWER_OFF_PEGASUS",
                    "POWER_OFF_ASIAIR",
                )
            ),
        }

        try:
            write_status(
                status_file,
                status_data,
            )

        except StatusWriteError as error:
            logger.error(
                f"Unable to publish Guardian status: {error}"
            )

    def create_operator_alert(
        self,
        source,
        event_type,
        message,
    ):
        """
        Create one persistent operator alert containing the final
        Guardian protection results.
        """

        try:
            alert = self.alert_manager.set_alert(
                severity="CRITICAL",
                source=source,
                event_type=event_type,
                message=message,
                protection_results=dict(
                    self.protection_results
                ),
            )

        except AlertManagerError as error:
            logger.error(
                "ALERT | CREATE_FAILED | "
                f"Unable to create persistent alert: {error}"
            )
            return False

        logger.critical(
            "ALERT | CREATED | "
            f"{source} {event_type} incident recorded."
        )

        return alert

    def acknowledge_operator_alert(self):
        """
        Acknowledge and clear the current persistent operator alert.
        """

        try:
            acknowledged = self.alert_manager.acknowledge()

        except AlertManagerError as error:
            self.events.emit(
                source="ALERT",
                event_type="ACK_FAILED",
                severity="ERROR",
                message=f"Unable to acknowledge operator alert: {error}",
            )
            return False

        if acknowledged:
            logger.info(
                "ALERT | ACKNOWLEDGED | "
                "Persistent operator alert acknowledged."
            )
        else:
            logger.info(
                "ALERT | ACK_NOT_REQUIRED | "
                "No active operator alert exists."
            )

        return acknowledged

    def process_control_command(self):
        """Process one pending Guardian control command."""

        control_file = self.config["control"]["command_file"]

        try:
            command = read_control_command(control_file)

        except ControlCommandError as error:
            self.events.emit(
                source="CONTROL",
                event_type="ERROR",
                severity="ERROR",
                message=f"Control command error: {error}",
            )
            return

        if command is None:
            return

        if command == "ARM":
            self.start_session()

        elif command == "DISARM":
            self.stop_session()

        elif command == "STATUS":
            self.events.emit(
                source="CONTROL",
                event_type="STATUS",
                severity="INFO",
                message=(
                    f"Guardian session active: "
                    f"{self.session.active}"
                ),
            )

        elif command == "ACK":
            self.acknowledge_operator_alert()

        elif command == "ACK_ABORT":
            self.acknowledge_emergency_abort()

        try:
            clear_control_command(control_file)

        except ControlCommandError as error:
            self.events.emit(
                source="CONTROL",
                event_type="ERROR",
                severity="ERROR",
                message=f"Unable to clear control command: {error}",
            )
