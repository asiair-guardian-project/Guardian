"""Guardian 1.0 event log, in the same style as the v0.6 log.

One line per event that matters to the rig, never one per check:

    2026-11-03 21:14:09 [CRITICAL] ROOF | CLOSED | Roof status changed to CLOSED.

It lives in logs/guardian_v1.log (daily rotation, 7 days kept, like v0.6) and
is a separate file from v0.6's guardian.log so the two programs never write
the same file. Nothing here can stop protection: every failure to write or
to observe is swallowed.
"""
from datetime import date, datetime, timedelta
from pathlib import Path

from modules.guardian_types import Capability, CapabilityStatus

KEEP_DAYS = 7
LOG_NAME = "guardian_v1.log"


class EventJournal:
    def __init__(self, log_dir, *, clock=datetime.now):
        self.dir = Path(log_dir)
        self.path = self.dir / LOG_NAME
        self._clock = clock

    def event(self, level, category, code, message):
        """Write one line. Returns True if written; never raises."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._rotate()
            stamp = self._clock().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{stamp} [{level:<8}] {category} | {code} | {message}\n"
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line)
            return True
        except Exception:
            return False

    def _rotate(self):
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with open(self.path, "r", encoding="utf-8") as handle:
            first = handle.readline()
        try:
            started = date.fromisoformat(first[:10])
        except ValueError:
            return
        today = self._clock().date()
        if started >= today:
            return
        archive = self.dir / f"{LOG_NAME}.{started.isoformat()}"
        if archive.exists():
            with open(archive, "a", encoding="utf-8") as out:
                out.write(self.path.read_text(encoding="utf-8"))
            self.path.unlink()
        else:
            self.path.rename(archive)
        cutoff = today - timedelta(days=KEEP_DAYS)
        for old in self.dir.glob(f"{LOG_NAME}.*"):
            try:
                if date.fromisoformat(old.name.rsplit(".", 1)[1]) < cutoff:
                    old.unlink()
            except (ValueError, OSError):
                continue


_CAPABILITIES = (
    (Capability.OBSERVATORY_SAFETY_MONITORING, "ROOF_FEED",
     "Roof safety feed"),
    (Capability.ASIAIR_MONITORING, "ASIAIR_CHECK", "ASIAIR reachability check"),
    (Capability.SAFETY_POWER_CONTROL, "STRIP", "Power strip safety-power control"),
)


class RigEventObserver:
    """Compares each cycle with the previous one and journals the changes."""

    def __init__(self, journal):
        self.journal = journal
        self._seen = {}
        self._incident = None
        self._records = 0

    def started(self, *, hardware_requested):
        self.journal.event(
            "INFO", "MONITOR", "STARTED",
            "Guardian v1.0 monitor started. Power cut by this monitor: "
            + ("ENABLED (needs ARM)" if hardware_requested
               else "DISABLED (watching only)"))

    def _changed(self, key, value):
        """True when value differs from last time. The first value is a baseline."""
        previous = self._seen.get(key, self)
        self._seen[key] = value
        return previous is not self and previous != value, previous is self

    def observe(self, *, application, gate, observation, failure=None):
        """observation: the cycle's observation, or None when the cycle failed."""
        try:
            self._observe(application, gate, observation, failure)
        except Exception:
            pass  # journaling must never affect protection

    def _observe(self, application, gate, observation, failure):
        log = self.journal.event

        def note(key, value, level, category, code, text):
            changed, first = self._changed(key, value)
            if first or changed:
                log(level, category, code, text)

        # A failed cycle: say so once, and again when it recovers.
        changed, first = self._changed("cycle", failure)
        if changed or (first and failure):
            if failure:
                log("WARNING", "MONITOR", "OBSERVATION_FAILED", str(failure))
            else:
                log("INFO", "MONITOR", "OBSERVATION_RESTORED",
                    "Observations are working again.")
        if observation is not None:
            roof = observation.roof_state.name
            note("roof", roof,
                 "WARNING" if roof not in ("OPEN", "CLOSED") else "INFO",
                 "ROOF", roof, f"Roof status changed to {roof}.")
            air = observation.asiair_state.name
            note("asiair", air,
                 "INFO" if air == "ONLINE" else "WARNING",
                 "ASIAIR", air,
                 f"ASIAIR status changed to {air}.")
            note("ups", bool(observation.ups_low_battery),
                 "CRITICAL" if observation.ups_low_battery else "INFO",
                 "UPS", "LOW_BATTERY" if observation.ups_low_battery else "OK",
                 "UPS battery is low." if observation.ups_low_battery
                 else "UPS battery is not low.")
        registry = application.capabilities
        for capability, category, label in _CAPABILITIES:
            status = registry.status(capability)
            good = status is CapabilityStatus.AVAILABLE
            changed, first = self._changed(("cap", capability), status)
            if (first and not good) or changed:
                log("INFO" if good else "WARNING", category, status.name,
                    f"{label} is {status.name}.")
        supervisor = application.supervisor
        session = supervisor.session_state.name
        note("session", session,
             "CRITICAL" if session == "ABORTED" else "INFO",
             "SESSION", session, f"Session is now {session}.")
        armed = bool(gate.armed)
        changed, first = self._changed("armed", armed)
        if changed:
            log("ACTION", "ARM", "ARMED" if armed else "DISARMED",
                "ARM authorization granted by operator." if armed
                else "ARM authorization revoked.")
        refusal = getattr(gate, "last_refusal", None)
        changed, first = self._changed("refusal", refusal)
        if changed and refusal:
            log("WARNING", "ARM", "REFUSED", f"ARM refused: {refusal}")
        blocked = bool(supervisor.recovery_blocked)
        changed, first = self._changed("recovery", blocked)
        if (first and blocked) or changed:
            if blocked:
                log("CRITICAL", "SESSION", "RECOVERY_BLOCKED",
                    "Emergency-state recovery has not succeeded. Reason: "
                    f"{supervisor.recovery_block_reason}")
            else:
                log("INFO", "SESSION", "RECOVERY_CLEARED",
                    "Emergency-state recovery is no longer blocked.")
        self._incident_events(supervisor.incident, supervisor)

    def _incident_events(self, incident, supervisor):
        log = self.journal.event
        if incident is not self._incident:
            if incident is not None:
                triggers = ", ".join(sorted(t.name for t in incident.triggers))
                log("CRITICAL", "PROTECTION", "INCIDENT_OPENED",
                    f"Protection incident opened. Triggers: {triggers}.")
                self._records = 0
            else:
                log("INFO", "PROTECTION", "INCIDENT_CLEARED",
                    "Protection incident acknowledged and cleared.")
            self._incident = incident
        if incident is None:
            return
        records = list(incident.records)
        if len(records) < self._records:
            self._records = 0
        for record in records[self._records:]:
            result = getattr(record.result, "name", str(record.result))
            bad = result in ("FAILED", "COMMANDED_UNVERIFIED", "TIMED_OUT",
                             "UNVERIFIED")
            level = "CRITICAL" if bad else "ACTION"
            log(level, "POWER", record.action.name, f"Result: {result}.")
        self._records = len(records)
