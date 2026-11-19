"""Per-night summary of the Guardian v1.0 event log (read-only).

Reads logs/guardian_v1.log and its daily archives and prints, for each night
(noon to noon, local time, labelled by the evening's date): roof closures with
start, end and duration, ASIAIR losses, and any time the monitor was not running.
It never writes anything and never touches hardware.
"""
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
import re

LINE = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[(\w+)\s*\] ([A-Z0-9_]+) \| ([A-Z0-9_]+) \| (.*)$")
BOUNCE_MINUTES = 30
RESTART_WINDOW_SECONDS = 60   # a state seen this soon after a start is the starting state
MIN_GAP_SECONDS = 120         # shorter stops are ordinary restarts, not gaps
ROOF_FEED_GRACE_SECONDS = 60  # the roof filter treats a feed down this long as CLOSED
FEEDS = {"ROOF_FEED": "roof feed", "ASIAIR_CHECK": "ASIAIR check", "STRIP": "power strip"}


def read_events(log_dir):
    """All parseable events, oldest first. Unreadable or malformed lines are skipped."""
    log_dir = Path(log_dir)
    events = []
    for path in sorted(log_dir.glob("guardian_v1.log*")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            match = LINE.match(raw)
            if not match:
                continue
            try:
                when = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            events.append((when, match.group(2), match.group(3),
                           match.group(4), match.group(5)))
    events.sort(key=lambda event: event[0])
    return events


def night_of(when):
    """Label a moment by the date of the evening its night began (noon to noon)."""
    return (when - timedelta(hours=12)).date()


def summarize(events):
    """OrderedDict: night date -> dict of closures, asiair_lost, gaps, incidents."""
    nights = OrderedDict()

    def bucket(when):
        key = night_of(when)
        return nights.setdefault(key, {
            "closures": [], "asiair_lost": [], "gaps": [], "incidents": [],
            "outages": []})

    roof = None          # last known roof state
    open_closure = None  # the closure currently in progress
    stopped_at = None
    started_at = None
    down = {}  # feed category -> when it went down
    for when, _level, category, code, message in events:
        if category == "MONITOR" and code == "STOPPED":
            stopped_at = when
        elif category == "MONITOR" and code == "STARTED":
            if (stopped_at is not None
                    and (when - stopped_at).total_seconds() >= MIN_GAP_SECONDS):
                bucket(stopped_at)["gaps"].append((stopped_at, when))
            stopped_at = None
            started_at = when
        elif category == "ROOF" and code in ("CLOSED", "OPEN"):
            if code == roof:
                continue  # a restart repeating the state it already had
            if code == "CLOSED":
                at_start = (started_at is not None and
                            (when - started_at).total_seconds() <= RESTART_WINDOW_SECONDS)
                # Closed when the monitor (re)started: when it really closed is unknown.
                open_closure = {"start": when, "end": None, "known": not at_start}
                bucket(when)["closures"].append(open_closure)
            elif open_closure is not None:
                open_closure["end"] = when
                open_closure = None
            roof = code
        elif category in FEEDS:
            if "state verification" in message:
                continue  # a false alarm that Patch 18 wrote and Patch 19 removed
            if code == "AVAILABLE":
                began = down.pop(category, None)
                if began is not None:
                    bucket(began)["outages"].append(
                        {"feed": category, "start": began, "end": when})
            elif category not in down:
                down[category] = when
        elif category == "ASIAIR" and code == "LOST":
            bucket(when)["asiair_lost"].append(when)
        elif category == "PROTECTION" and code == "INCIDENT_OPENED":
            bucket(when)["incidents"].append(when)
    for category, began in down.items():  # still down at the end of the log
        bucket(began)["outages"].append(
            {"feed": category, "start": began, "end": None})
    for night in nights.values():
        night["outages"].sort(key=lambda o: o["start"])
    return nights


def _minutes(delta):
    return delta.total_seconds() / 60.0


def _duration(start, end, exact=False):
    if exact and (end - start).total_seconds() < 120:
        return f"{(end - start).total_seconds():.0f} s"
    minutes = _minutes(end - start)
    if minutes < 1:
        return "under 1 min"
    if minutes < 90:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.1f} h"


def render(nights, *, last=None):
    if not nights:
        return "No Guardian v1.0 events found."
    keys = list(nights)
    if last is not None:
        keys = keys[-last:]
    out = []
    for key in keys:
        n = nights[key]
        closures = [c for c in n["closures"] if c["known"]]
        unknown = [c for c in n["closures"] if not c["known"]]
        bounces = [c for c in closures if c["end"] is not None
                   and _minutes(c["end"] - c["start"]) <= BOUNCE_MINUTES]
        out.append(f"Night of {key:%Y-%m-%d}: {len(closures)} roof closure(s), "
                   f"{len(bounces)} reopened within {BOUNCE_MINUTES} min")
        for c in unknown:
            end = "still closed at end of log" if c["end"] is None \
                else f"reopened {c['end']:%H:%M:%S}"
            out.append(f"  closed when the monitor started ({c['start']:%H:%M:%S}), "
                       f"true start unknown - {end}")
        for c in closures:
            if c["end"] is None:
                out.append(f"  closed {c['start']:%H:%M:%S} - still closed at end of log")
            else:
                out.append(f"  closed {c['start']:%H:%M:%S} - reopened {c['end']:%H:%M:%S}"
                           f"  ({_duration(c['start'], c['end'])})")
        for o in n["outages"]:
            label = FEEDS[o["feed"]]
            if o["end"] is None:
                out.append(f"  {label} down from {o['start']:%H:%M:%S} - still down at end of log")
                continue
            seconds = (o["end"] - o["start"]).total_seconds()
            note = ""
            if o["feed"] == "ROOF_FEED" and seconds >= ROOF_FEED_GRACE_SECONDS:
                note = "  <- longer than the 60 s grace: counts as CLOSED"
            out.append(f"  {label} down {o['start']:%H:%M:%S} - {o['end']:%H:%M:%S}"
                       f"  ({_duration(o['start'], o['end'], exact=True)}){note}")
        for when in n["asiair_lost"]:
            out.append(f"  ASIAIR lost at {when:%H:%M:%S}")
        for when in n["incidents"]:
            out.append(f"  PROTECTION INCIDENT at {when:%H:%M:%S}")
        for start, end in n["gaps"]:
            out.append(f"  monitor was NOT running {start:%H:%M:%S} - {end:%H:%M:%S}"
                       "  (events in that gap are not recorded)")
        out.append("")
    return "\n".join(out).rstrip()
