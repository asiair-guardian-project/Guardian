"""Guardian 1.0 hardware-execution safety mode."""


class GuardianV1Mode:
    """
    Controls whether Guardian 1.0 may issue hardware-changing commands.

    Guardian 1.0 always starts in monitor-only mode. Hardware execution
    requires an explicit enable operation.
    """

    def __init__(self):
        self._hardware_execution_enabled = False

    @property
    def hardware_execution_enabled(self) -> bool:
        return self._hardware_execution_enabled

    @property
    def monitor_only(self) -> bool:
        return not self._hardware_execution_enabled

    def enable_hardware_execution(self) -> None:
        self._hardware_execution_enabled = True

    def disable_hardware_execution(self) -> None:
        self._hardware_execution_enabled = False

    def execute_hardware_action(self, action) -> bool:
        """
        Execute a hardware-changing action only when explicitly enabled.

        Returns True when the action was permitted and invoked.
        Returns False when monitor-only mode blocked the action.
        """
        if not self._hardware_execution_enabled:
            return False

        action()
        return True
