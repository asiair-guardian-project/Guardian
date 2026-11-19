"""Guardian 1.0 hardware execution boundary."""

from modules.guardian_types import SafetyPowerResult
from modules.safety_power_manager import SafetyPowerRoleRecord
from modules.guardian_v1_mode import GuardianV1Mode


class GuardianV1Execution:
    """
    Gate all Guardian 1.0 hardware-changing actions through its execution mode.

    In monitor-only mode, hardware callbacks are never invoked.

    When hardware execution is explicitly enabled, the real executors are
    called and their results are returned unchanged.
    """

    def __init__(
        self,
        *,
        mode: GuardianV1Mode,
        execute_action,
        execute_safety_power=None,
    ):
        self._mode = mode
        self._execute_action = execute_action
        self._execute_safety_power = execute_safety_power

    def execute_action(self, action):
        if self._mode.monitor_only:
            return SafetyPowerResult.SIMULATED

        return self._execute_action(action)

    def execute_safety_power(self, roles):
        if self._mode.monitor_only:
            return [
                SafetyPowerRoleRecord(
                    role=role,
                    endpoint=None,
                    result=SafetyPowerResult.SIMULATED,
                )
                for role in roles
            ]

        if self._execute_safety_power is None:
            return []

        return self._execute_safety_power(roles)
