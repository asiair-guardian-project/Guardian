from modules.state_tracker import StateTracker


tracker = StateTracker()

print(f"Initial state: {tracker.state}")

print("Change:", tracker.update(True))
print("State :", tracker.state)

print("Change:", tracker.update(True))
print("State :", tracker.state)

print("Change:", tracker.update(False))
print("State :", tracker.state)

print("Change:", tracker.update(False))
print("State :", tracker.state)

print("Change:", tracker.update(True))
print("State :", tracker.state)