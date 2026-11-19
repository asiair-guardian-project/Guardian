from modules.guardian import Guardian


guardian = Guardian()

print("Initial latch:")
print(guardian.roof_close_protection_triggered)
print()

print("Start session:")
guardian.start_session()
print(guardian.roof_close_protection_triggered)
print()

print("Simulate imaging permission:")
guardian.session.permit_imaging()
print(guardian.session.state)
print()

print("First roof-close trigger:")
if (
    guardian.session.state == guardian.session.IMAGING_PERMITTED
    and not guardian.roof_close_protection_triggered
):
    guardian.roof_close_protection_triggered = True
    print("Protection would execute.")

print(guardian.roof_close_protection_triggered)
print()

print("Second roof-close trigger:")
if (
    guardian.session.state == guardian.session.IMAGING_PERMITTED
    and not guardian.roof_close_protection_triggered
):
    print("Protection would execute.")
else:
    print("Protection suppressed by latch.")

print()

print("Stop session:")
guardian.stop_session()
print(guardian.roof_close_protection_triggered)