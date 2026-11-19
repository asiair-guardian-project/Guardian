from modules.state_tracker import StateTracker


tracker = StateTracker()

roof_states = [
    "CLOSED",
    "CLOSED",
    "OPEN",
    "OPEN",
    "CLOSING",
    "CLOSING",
    "CLOSED",
]

for status in roof_states:
    changed = tracker.update(status)

    if changed:
        print(f"ROOF STATE CHANGED: {status}")
    else:
        print(f"ROOF unchanged: {status}")