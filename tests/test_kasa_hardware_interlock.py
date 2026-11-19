import pytest

from modules.kasa_controller import (
    KasaController,
    KasaSafetyError,
)


def test_hardware_switching_is_blocked_during_pytest(monkeypatch):
    controller = KasaController("192.0.2.1")

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/test_kasa_hardware_interlock.py::test_guard",
    )
    monkeypatch.delenv(
        "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS",
        raising=False,
    )

    with pytest.raises(
        KasaSafetyError,
        match="hardware switching is blocked during automated tests",
    ):
        controller._require_hardware_switching_allowed()


def test_live_hardware_override_must_be_explicit(monkeypatch):
    controller = KasaController("192.0.2.1")

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/test_kasa_hardware_interlock.py::test_override",
    )
    monkeypatch.setenv(
        "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS",
        "YES_I_UNDERSTAND",
    )

    controller._require_hardware_switching_allowed()


def test_non_test_runtime_is_not_blocked(monkeypatch):
    controller = KasaController("192.0.2.1")

    monkeypatch.delenv(
        "PYTEST_CURRENT_TEST",
        raising=False,
    )
    monkeypatch.delenv(
        "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS",
        raising=False,
    )

    controller._require_hardware_switching_allowed()


def test_physical_turn_off_cannot_execute_during_pytest(monkeypatch):
    controller = KasaController("192.0.2.1")

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/test_kasa_hardware_interlock.py::test_physical_turn_off",
    )
    monkeypatch.delenv(
        "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS",
        raising=False,
    )

    class FakeOutlet:
        alias = "Wave 150i"

        def __init__(self):
            self.turn_off_called = False

        async def update(self):
            pass

        async def turn_off(self):
            self.turn_off_called = True

    class FakeStrip:
        def __init__(self, outlet):
            self.children = [None, None, outlet]

    outlet = FakeOutlet()
    strip = FakeStrip(outlet)

    with pytest.raises(
        KasaSafetyError,
        match="hardware switching is blocked during automated tests",
    ):
        import asyncio

        asyncio.run(
            controller._power_off_from_strip(
                strip,
                3,
                "Wave 150i",
            )
        )

    assert outlet.turn_off_called is False


def test_python_kasa_transport_cannot_turn_off_during_pytest(monkeypatch):
    import asyncio

    from modules.kasa_safety_power_adapter import (
        KasaTransportError,
        PythonKasaTransport,
    )

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/test_kasa_hardware_interlock.py::test_transport_guard",
    )
    monkeypatch.delenv(
        "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS",
        raising=False,
    )

    transport = PythonKasaTransport(
        host="192.0.2.1",
        username="unused",
        password="unused",
    )

    class FakeOutlet:
        is_on = True

        def __init__(self):
            self.turn_off_called = False

        async def turn_off(self):
            self.turn_off_called = True

    outlet = FakeOutlet()

    class FakeDevice:
        def __init__(self):
            self.closed = False

    device = FakeDevice()

    async def fake_validated_outlet(
        outlet_number,
        expected_alias,
    ):
        return device, outlet

    async def fake_close_hs300(device_to_close):
        assert device_to_close is device
        device.closed = True

    monkeypatch.setattr(
        transport,
        "_validated_outlet",
        fake_validated_outlet,
    )

    monkeypatch.setattr(
        "modules.kasa_safety_power_adapter.close_hs300",
        fake_close_hs300,
    )

    with pytest.raises(
        KasaTransportError,
        match="hardware switching is blocked during automated tests",
    ):
        asyncio.run(
            transport._power_off_outlet_async(
                3,
                "Wave 150i",
            )
        )

    assert outlet.turn_off_called is False
    assert device.closed is True
