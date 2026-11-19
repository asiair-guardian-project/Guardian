from modules.network_state import NetworkState

tracker = NetworkState()

sequence = [
    True,
    True,
    True,
    False,
    False,
    True,
    True,
    False,
]

for state in sequence:

    event = tracker.check(state)

    print(f"{state} -> {event}")