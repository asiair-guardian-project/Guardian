from modules.session_manager import SessionManager


session = SessionManager(
    observatory_name="Starfront Observatory",
    guardian_version="0.6",
)

print("Initial state:")
print(session.state)
print()

print("Start session:")
session.start()
print(session.state)
print()

print("Roof CLOSED + FRESH:")
if session.state == session.WAITING_FOR_ROOF:
    roof_status = "CLOSED"
    freshness_state = "FRESH"

    if (
        roof_status == "OPEN"
        and freshness_state == "FRESH"
    ):
        session.permit_imaging()

print(session.state)
print()

print("Roof OPEN + STALE:")
if session.state == session.WAITING_FOR_ROOF:
    roof_status = "OPEN"
    freshness_state = "STALE"

    if (
        roof_status == "OPEN"
        and freshness_state == "FRESH"
    ):
        session.permit_imaging()

print(session.state)
print()

print("Roof OPEN + FRESH:")
if session.state == session.WAITING_FOR_ROOF:
    roof_status = "OPEN"
    freshness_state = "FRESH"

    if (
        roof_status == "OPEN"
        and freshness_state == "FRESH"
    ):
        session.permit_imaging()

print(session.state)