class StateTracker:
    """Tracks state changes for Guardian subsystems."""

    def __init__(self, initial_state=None):
        self._state = initial_state

    @property
    def state(self):
        return self._state

    def update(self, new_state):
        """
        Update the tracked state.

        Returns:
            True if the state changed.
            False if the state remained the same.
        """

        if self._state == new_state:
            return False

        self._state = new_state
        return True