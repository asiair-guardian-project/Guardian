"""Read-only check: do the outlet names in the operator's mapping match what the power controller reports?

Reads the controller once (no switching, ever) and compares each mapped role and the host outlet with the controller's
own outlet names. Works for Kasa HS300 and Digital Loggers. Credentials come from the usual environment / Keychain
sources; nothing is stored.
"""
from __future__ import annotations

from typing import Callable, List, Mapping


def compare(outlets: List[Mapping], layout) -> List[dict]:
    """One row per mapped role (and the host): what we expect, what the controller says, and whether they match."""
    by_number = {int(o["number"]): o for o in outlets}
    rows = []
    wanted = [("host computer", layout.host[0], layout.host[1])] + \
             [(t.role.name.lower(), t.number, t.alias) for t in layout.targets]
    for role, number, alias in wanted:
        found = by_number.get(number)
        actual = None if found is None else found["name"]
        rows.append({"role": role, "number": number, "expected": alias, "actual": actual,
                     "match": actual == alias, "is_on": None if found is None else bool(found["is_on"])})
    names = [o["name"] for o in outlets]
    for row in rows:
        row["unique"] = row["actual"] is None or names.count(row["actual"]) == 1
    return rows


def run(read_outlets: Callable[[], List[Mapping]], layout, say=print) -> int:
    """0 only if every mapped outlet's name matches exactly and is unique on the controller."""
    try:
        outlets = read_outlets()
    except Exception as error:
        say(f"Could not read the controller: {error}")
        return 1
    rows = compare(outlets, layout)
    say("Your mapping against the controller (read-only, nothing was switched):")
    bad = 0
    for row in rows:
        ok = row["match"] and row["unique"]
        bad += not ok
        state = "" if row["is_on"] is None else (" (ON)" if row["is_on"] else " (OFF)")
        if ok:
            verdict = "matches"
        elif row["actual"] is None:
            verdict = "NOT FOUND on the controller"
        elif not row["match"]:
            verdict = f"DOES NOT MATCH (controller calls it {row['actual']!r})"
        else:
            verdict = "NAME IS NOT UNIQUE on the controller"
        say(f"  {row['role']}: outlet {row['number']} {row['expected']!r}{state} -> {verdict}")
    say("All mapped outlet names match." if not bad
        else f"{bad} problem(s). Fix the names (in the controller's app or in your mapping) before commissioning.")
    return 0 if not bad else 1
