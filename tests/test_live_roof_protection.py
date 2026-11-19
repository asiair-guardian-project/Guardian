from modules.guardian import Guardian


guardian = Guardian()
guardian.start()

# Simulate an active imaging session.
guardian.session.start()

print("\nSimulated imaging session is ACTIVE.")
print("Running one Guardian monitoring cycle...\n")

guardian.monitor_once()