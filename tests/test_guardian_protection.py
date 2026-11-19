from modules.guardian import Guardian


guardian = Guardian()

print("CASE: Roof closed while idle")
actions = guardian.evaluate_protection(
    source="ROOF",
    event_type="CLOSED",
)
print(actions)

print("\nCASE: Roof closed while imaging")
guardian.session.start()

actions = guardian.evaluate_protection(
    source="ROOF",
    event_type="CLOSED",
)
print(actions)