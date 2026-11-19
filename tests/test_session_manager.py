from modules.session_manager import SessionManager


session = SessionManager(
    observatory_name="Starfront Observatory",
    guardian_version="0.6",
)

print("Initial")
print(session.status())
print()

print("Start session")
print(f"Start result: {session.start()}")
print(session.status())
print()

print("Permit imaging")
print(f"Permit result: {session.permit_imaging()}")
print(session.status())
print()

print("Second permit")
print(f"Permit result: {session.permit_imaging()}")
print()

print("Stop session")
print(f"Stop result: {session.stop()}")
print(session.status())
print()

print("Second stop")
print(f"Stop result: {session.stop()}")

print()
print("Abort test")

session.start()
print(f"State after start: {session.state}")

session.permit_imaging()
print(f"State after permit: {session.state}")

print(f"Abort result: {session.abort()}")
print(f"State after abort: {session.state}")
print(f"Active: {session.active}")
print(f"Imaging permitted: {session.imaging_permitted}")

print(f"Stop aborted session: {session.stop()}")
print(f"Final state: {session.state}")