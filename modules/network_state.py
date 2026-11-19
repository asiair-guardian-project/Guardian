class NetworkState:
    """Tracks internet connectivity changes."""

    def __init__(self):
        self.previous_state = None

    def check(self, current_state):
        """Return an event only when the network state changes."""

        if self.previous_state is None:
            self.previous_state = current_state

            if current_state:
                return "CONNECTED"

            return "LOST"

        if current_state != self.previous_state:
            self.previous_state = current_state

            if current_state:
                return "RESTORED"

            return "LOST"

        return None