from modules.guardian_v1_mode import GuardianV1Mode


def test_guardian_v1_defaults_to_monitor_only():
    mode = GuardianV1Mode()

    assert mode.monitor_only is True
    assert mode.hardware_execution_enabled is False


def test_hardware_execution_requires_explicit_enable():
    mode = GuardianV1Mode()

    mode.enable_hardware_execution()

    assert mode.monitor_only is False
    assert mode.hardware_execution_enabled is True


def test_hardware_execution_can_be_disabled_again():
    mode = GuardianV1Mode()

    mode.enable_hardware_execution()
    mode.disable_hardware_execution()

    assert mode.monitor_only is True
    assert mode.hardware_execution_enabled is False


def test_monitor_only_blocks_hardware_action():
    mode = GuardianV1Mode()
    calls = []

    result = mode.execute_hardware_action(
        lambda: calls.append("executed")
    )

    assert result is False
    assert calls == []


def test_enabled_mode_allows_hardware_action():
    mode = GuardianV1Mode()
    calls = []

    mode.enable_hardware_execution()

    result = mode.execute_hardware_action(
        lambda: calls.append("executed")
    )

    assert result is True
    assert calls == ["executed"]


def test_disabling_mode_blocks_hardware_action_again():
    mode = GuardianV1Mode()
    calls = []

    mode.enable_hardware_execution()
    mode.disable_hardware_execution()

    result = mode.execute_hardware_action(
        lambda: calls.append("executed")
    )

    assert result is False
    assert calls == []
