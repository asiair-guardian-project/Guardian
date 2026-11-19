"""Tests for Guardian 1.0 read-only Kasa observation."""

from modules.kasa_read_only_adapter import KasaReadOnlyAdapter
from modules.kasa_safety_power_adapter import KasaEndpointConfig
from modules.safety_power import SafetyPowerEndpoint


class FakeTransport:
    def __init__(self):
        self.calls = []

    def check_outlet(self, number, alias):
        self.calls.append((number, alias))
        return number == 2 and alias == "ASIAIR"


def make_adapter(transport):
    return KasaReadOnlyAdapter(
        controller_id="hs300",
        endpoints={
            "asiair": KasaEndpointConfig(2, "ASIAIR"),
            "mount": KasaEndpointConfig(3, "Wave 150i"),
        },
        transport=transport,
    )


def test_validates_configured_outlet():
    transport = FakeTransport()
    adapter = make_adapter(transport)

    assert adapter.check_endpoint(
        SafetyPowerEndpoint("hs300", "asiair")
    )
    assert transport.calls == [(2, "ASIAIR")]


def test_rejects_wrong_controller():
    transport = FakeTransport()
    adapter = make_adapter(transport)

    assert not adapter.check_endpoint(
        SafetyPowerEndpoint("other", "asiair")
    )
    assert transport.calls == []


def test_rejects_unknown_endpoint():
    transport = FakeTransport()
    adapter = make_adapter(transport)

    assert not adapter.check_endpoint(
        SafetyPowerEndpoint("hs300", "unknown")
    )
    assert transport.calls == []


def test_exposes_no_power_control_methods():
    adapter = make_adapter(FakeTransport())

    assert not hasattr(adapter, "power_off")
    assert not hasattr(adapter, "verify_off")
    assert not hasattr(adapter, "get_power_state")
