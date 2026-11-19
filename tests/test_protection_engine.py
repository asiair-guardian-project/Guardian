from modules.protection_engine import ProtectionEngine


engine = ProtectionEngine()


def show_case(name, source, event_type, session_active):
    actions = engine.evaluate(
        source=source,
        event_type=event_type,
        session_active=session_active,
    )

    print(f"\nCASE: {name}")
    print(f"Source: {source}")
    print(f"Event: {event_type}")
    print(f"Session active: {session_active}")
    print(f"Actions: {actions}")


show_case(
    "Roof closed while idle",
    "ROOF",
    "CLOSED",
    False,
)

show_case(
    "Roof closed while imaging",
    "ROOF",
    "CLOSED",
    True,
)

show_case(
    "Roof status unknown",
    "ROOF",
    "UNKNOWN",
    True,
)

show_case(
    "Roof closed while Wave is moving",
    "ROOF",
    "CLOSED_WAVE_MOVING",
    True,
)

show_case(
    "Roof closed while Wave motion is unknown",
    "ROOF",
    "CLOSED_WAVE_MOTION_UNKNOWN",
    True,
)


show_case(
    "ASIAIR offline while imaging",
    "ASIAIR",
    "OFFLINE",
    True,
)


show_case(
    "Wave offline while imaging",
    "WAVE",
    "OFFLINE",
    True,
)


show_case(
    "UPS on battery",
    "UPS",
    "ON_BATTERY",
    True,
)
