class ProtectionEngine:
    """Evaluates Guardian events and recommends safety actions."""

    def evaluate(self, source, event_type, session_active):
        """
        Return a list of recommended actions.

        This version is decision-only.
        It does not control hardware.
        """

        actions = []

        if source == "ROOF":
            if event_type == "UNKNOWN":
                actions.append("WARN_OPERATOR")

            elif event_type in (
                "CLOSED",
                "CLOSED_WAVE_MOVING",
                "CLOSED_WAVE_MOTION_UNKNOWN",
            ) and session_active:
                actions.append("STOP_WAVE")
                actions.append("POWER_OFF_PEGASUS")
                actions.append("POWER_OFF_ASIAIR")
                actions.append("WAIT_FOR_OPERATOR")

        elif source == "ASIAIR":
            if event_type == "OFFLINE" and session_active:
                actions.append("STOP_WAVE")
                actions.append("POWER_OFF_PEGASUS")
                actions.append("POWER_OFF_ASIAIR")
                actions.append("WAIT_FOR_OPERATOR")

        elif source == "UPS":
            if event_type == "ON_BATTERY":
                actions.append("WARN_OPERATOR")

            elif event_type == "LOW_BATTERY" and session_active:
                actions += ["STOP_WAVE", "POWER_OFF_PEGASUS", "POWER_OFF_ASIAIR", "WAIT_FOR_OPERATOR"]

        return actions