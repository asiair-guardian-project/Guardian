"""Read-only monitoring watch: what would Guardian conclude, moment by moment?

Samples the REAL ASIAIR (ping) and the REAL roof feed (Alpaca) using the same
observation cycle Guardian uses, with no power control, no session and no
hardware. Records every cycle and every change, so the ASIAIR and roof
monitoring commissioning checks have evidence to rest on:
  * normal readings, with how old the roof reading is;
  * the ASIAIR going unreachable and coming back (operator switches it by hand);
  * a failed or stale roof feed (run against a deliberately wrong address).
It never switches anything and never approves commissioning.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from modules.asiair_state import DEFAULT_LOST_AFTER_MISSES, AsiairStateTracker
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import Capability
from modules.guardian_v1_observation_cycle import run_observation_cycle
from modules.guardian_v1_roof_filter import GuardianV1RoofFilter
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)

SCHEMA = "guardian-monitoring-watch-v1"
WATCHED = (Capability.ASIAIR_MONITORING, Capability.OBSERVATORY_SAFETY_MONITORING)


class _PingRecorder:
    """Passes checks through and remembers the raw answer (True/False/None=error)."""

    def __init__(self, inner):
        self._inner = inner
        self.last = None

    def is_reachable(self):
        self.last = None
        answer = self._inner.is_reachable()
        self.last = bool(answer)
        return answer


def summarize_pings(rows):
    """Count raw ASIAIR check misses and the longest silence, from recorded rows."""

    checks = [r for r in rows if "asiair_ping_raw" in r]
    missed = sum(1 for r in checks if r["asiair_ping_raw"] is False)
    errors = sum(1 for r in checks if r["asiair_ping_raw"] is None)
    longest_streak, streak = 0, 0
    longest_seconds, silent_since = 0.0, None

    for r in checks:
        t = datetime.fromisoformat(r["time_utc"])
        if r["asiair_ping_raw"] is False:
            streak += 1
            silent_since = silent_since or t
            longest_streak = max(longest_streak, streak)
            longest_seconds = max(longest_seconds, (t - silent_since).total_seconds())
        elif r["asiair_ping_raw"] is True:
            if silent_since is not None:
                longest_seconds = max(longest_seconds, (t - silent_since).total_seconds())
            streak, silent_since = 0, None

    return {"checks": len(checks), "missed": missed, "errors": errors,
            "longest_miss_streak": longest_streak,
            "longest_silence_seconds": round(longest_seconds, 1)}


def run_watch(*, asiair_adapter, observatory_adapter, seconds, interval_seconds=5.0,
              roof_max_age_seconds=30, lost_after_misses=DEFAULT_LOST_AFTER_MISSES, power_reader=None, sleep=time.sleep, clock=time.monotonic,
              now_fn=lambda: datetime.now(timezone.utc), on_line=None,
              on_checkpoint=None, checkpoint_every=60, should_stop=None):
    asiair_adapter = recorder = _PingRecorder(asiair_adapter)
    registry = CapabilityRegistry(set(WATCHED))
    tracker = AsiairStateTracker(lost_after_misses)
    coordinator = ObservatoryObservationCoordinator()
    roof_filter = GuardianV1RoofFilter()
    rows, changes = [], []
    previous = None
    started = clock()
    interrupted = False

    def report(final):
        return {"schema": SCHEMA, "commissioning_authorized": False,
                "note": "Monitoring evidence only. It does not approve commissioning.",
                "complete": final, "interrupted": interrupted,
                "cycles": len(rows),
                "cycles_with_all_three_paths_available": sum(
                    1 for r in rows if r.get("all_paths_available")),
                "power_strip_checked": power_reader is not None,
                "asiair_ping_summary": summarize_pings(rows),
                "changes": changes, "rows": rows}

    while True:
        now = now_fn()
        error = None
        try:
            cycle = run_observation_cycle(
                registry=registry, asiair_tracker=tracker,
                observatory_coordinator=coordinator,
                asiair_adapter=asiair_adapter, observatory_adapter=observatory_adapter,
                now=now, roof_max_age_seconds=roof_max_age_seconds)
            observation = cycle.observation
            effective = roof_filter.evaluate(observation.roof_state, now=now)
            last = coordinator.last_observation
            power_ok = None

            if power_reader is not None:
                try:
                    states = power_reader()
                    power_ok = bool(states) and all(
                        value is not None for value in states.values())
                except Exception:
                    power_ok = False

            row = {
                "time_utc": now.isoformat(),
                "asiair_state": observation.asiair_state.name,
                "roof_state": observation.roof_state.name,
                "roof_effective_state": effective.effective_state.name,
                "roof_unknown_timed_out": bool(effective.timed_out),
                "asiair_capability": registry.status(Capability.ASIAIR_MONITORING).name,
                "roof_capability": registry.status(
                    Capability.OBSERVATORY_SAFETY_MONITORING).name,
                "power_strip_readable": power_ok,
                "roof_reading_age_seconds": (
                    round((now - last.observed_at).total_seconds(), 1) if last else None),
            }
        except Exception as exc:  # an escaping error is itself evidence
            error = f"{type(exc).__name__}: {exc}"
            row = {"time_utc": now.isoformat(), "cycle_error": error}

        row["asiair_ping_raw"] = recorder.last
        rows.append(row)
        row["all_paths_available"] = bool(
            error is None
            and row.get("asiair_capability") == "AVAILABLE"
            and row.get("roof_capability") == "AVAILABLE"
            and row.get("power_strip_readable") is True)
        keys = ("asiair_state", "roof_state", "roof_effective_state",
                "asiair_capability", "roof_capability", "cycle_error",
                "power_strip_readable")
        snapshot = {k: row.get(k) for k in keys}
        if snapshot != previous:
            changes.append({"time_utc": row["time_utc"], **snapshot})
            if on_line:
                on_line(f"{row['time_utc'][11:19]}  ASIAIR={row.get('asiair_state')} "
                        f"(ping check {row.get('asiair_capability')})  "
                        f"roof={row.get('roof_state')}  "
                        f"(roof feed {row.get('roof_capability')}, age "
                        f"{row.get('roof_reading_age_seconds')} s)  "
                        f"strip readable={row.get('power_strip_readable')}"
                        + (f"  ERROR {error}" if error else ""))
            previous = snapshot

        if on_checkpoint is not None and len(rows) % checkpoint_every == 0:
            try:
                on_checkpoint(report(False))
            except Exception:  # a failed save must never stop the watch
                pass

        if should_stop is not None and should_stop():
            interrupted = True
            break

        if clock() - started >= seconds:
            break

        sleep(interval_seconds)

    return report(True)


def watch_path(directory, label) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"watch_{label}_{stamp}.json"


def write_watch(report, directory, label, path=None) -> Path:
    path = Path(path) if path else watch_path(directory, label)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True))
    temporary.chmod(0o600)
    temporary.replace(path)  # never leaves a half-written evidence file
    return path
