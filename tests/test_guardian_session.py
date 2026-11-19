from modules.guardian import Guardian


guardian = Guardian()

print(f"Initial active state: {guardian.session.active}")

guardian.start_session()
print(f"After start: {guardian.session.active}")

guardian.start_session()
print(f"After duplicate start: {guardian.session.active}")

guardian.stop_session()
print(f"After stop: {guardian.session.active}")

guardian.stop_session()
print(f"After duplicate stop: {guardian.session.active}")