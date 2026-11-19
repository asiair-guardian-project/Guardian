import pytest

from modules.kasa_safety_power_adapter import KasaEndpointConfig


def test_kasa_endpoint_config_records_number_and_alias():
    config = KasaEndpointConfig(
        outlet_number=3,
        expected_alias="Wave 150i",
    )

    assert config.outlet_number == 3
    assert config.expected_alias == "Wave 150i"


def test_kasa_endpoint_config_rejects_invalid_outlet_number():
    with pytest.raises(ValueError):
        KasaEndpointConfig(
            outlet_number=0,
            expected_alias="Wave 150i",
        )


def test_kasa_endpoint_config_rejects_empty_alias():
    with pytest.raises(ValueError):
        KasaEndpointConfig(
            outlet_number=3,
            expected_alias="   ",
        )

from modules.guardian_types import (
    SafetyPowerResult,
    SafetyPowerState,
)
from modules.kasa_safety_power_adapter import KasaSafetyPowerAdapter
from modules.safety_power import SafetyPowerEndpoint


class FakeKasaTransport:
    def __init__(self):
        self.checked = []
        self.state_requests = []
        self.power_off_requests = []
        self.state = SafetyPowerState.ON
        self.command_sent = True

    def check_outlet(self, outlet_number, expected_alias):
        self.checked.append((outlet_number, expected_alias))
        return True

    def get_outlet_state(self, outlet_number, expected_alias):
        self.state_requests.append((outlet_number, expected_alias))
        return self.state

    def power_off_outlet(self, outlet_number, expected_alias):
        self.power_off_requests.append(
            (outlet_number, expected_alias)
        )
        return self.command_sent


def make_adapter():
    transport = FakeKasaTransport()

    adapter = KasaSafetyPowerAdapter(
        controller_id="pier-power",
        endpoints={
            "mount": KasaEndpointConfig(3, "Wave 150i"),
            "asiair": KasaEndpointConfig(2, "ASIAIR"),
        },
        transport=transport,
    )

    return adapter, transport


def test_adapter_resolves_generic_endpoint_to_kasa_identity():
    adapter, transport = make_adapter()

    endpoint = SafetyPowerEndpoint(
        controller_id="pier-power",
        endpoint_id="mount",
    )

    assert adapter.check_endpoint(endpoint) is True
    assert transport.checked == [(3, "Wave 150i")]


def test_adapter_rejects_wrong_controller():
    adapter, transport = make_adapter()

    endpoint = SafetyPowerEndpoint(
        controller_id="other-controller",
        endpoint_id="mount",
    )

    with pytest.raises(ValueError):
        adapter.check_endpoint(endpoint)

    assert transport.checked == []


def test_adapter_rejects_unknown_endpoint_id():
    adapter, transport = make_adapter()

    endpoint = SafetyPowerEndpoint(
        controller_id="pier-power",
        endpoint_id="unknown",
    )

    with pytest.raises(ValueError):
        adapter.check_endpoint(endpoint)

    assert transport.checked == []


def test_adapter_reports_transport_power_state():
    adapter, transport = make_adapter()
    transport.state = SafetyPowerState.ON

    endpoint = SafetyPowerEndpoint(
        controller_id="pier-power",
        endpoint_id="asiair",
    )

    assert adapter.get_power_state(endpoint) is SafetyPowerState.ON
    assert transport.state_requests == [(2, "ASIAIR")]


def test_power_off_returns_commanded_unverified():
    adapter, transport = make_adapter()

    endpoint = SafetyPowerEndpoint(
        controller_id="pier-power",
        endpoint_id="mount",
    )

    assert (
        adapter.power_off(endpoint)
        is SafetyPowerResult.COMMANDED_UNVERIFIED
    )

    assert transport.power_off_requests == [(3, "Wave 150i")]


def test_failed_power_command_returns_failed():
    adapter, transport = make_adapter()
    transport.command_sent = False

    endpoint = SafetyPowerEndpoint(
        controller_id="pier-power",
        endpoint_id="mount",
    )

    assert adapter.power_off(endpoint) is SafetyPowerResult.FAILED


def test_verify_off_requires_observed_off_state():
    adapter, transport = make_adapter()

    endpoint = SafetyPowerEndpoint(
        controller_id="pier-power",
        endpoint_id="mount",
    )

    transport.state = SafetyPowerState.OFF
    assert (
        adapter.verify_off(endpoint)
        is SafetyPowerResult.VERIFIED_OFF
    )

    transport.state = SafetyPowerState.ON
    assert adapter.verify_off(endpoint) is SafetyPowerResult.FAILED

    transport.state = SafetyPowerState.UNKNOWN
    assert adapter.verify_off(endpoint) is SafetyPowerResult.FAILED

from modules.kasa_safety_power_adapter import (
    KasaTransportError,
    PythonKasaTransport,
)


class FakeOutlet:
    def __init__(self, alias, is_on=True):
        self.alias = alias
        self.is_on = is_on
        self.updated = 0
        self.turned_off = 0

    async def update(self):
        self.updated += 1

    async def turn_off(self):
        self.turned_off += 1
        self.is_on = False


class FakeDevice:
    def __init__(self, children):
        self.children = children
        self.closed = 0


async def fake_close_hs300(device):
    device.closed += 1


def make_python_transport():
    return PythonKasaTransport(
        host="192.0.2.10",
        username="test-user",
        password="test-password",
        timeout_seconds=2,
    )


def install_fake_kasa(monkeypatch, device):
    async def fake_connect_hs300(*args, **kwargs):
        return device

    monkeypatch.setattr(
        "modules.kasa_safety_power_adapter.connect_hs300",
        fake_connect_hs300,
    )
    monkeypatch.setattr(
        "modules.kasa_safety_power_adapter.close_hs300",
        fake_close_hs300,
    )


def test_python_transport_validates_number_and_alias(monkeypatch):
    outlets = [
        FakeOutlet("Mac Mini"),
        FakeOutlet("ASIAIR"),
        FakeOutlet("Wave 150i"),
    ]
    device = FakeDevice(outlets)
    install_fake_kasa(monkeypatch, device)

    transport = make_python_transport()

    assert transport.check_outlet(3, "Wave 150i") is True
    assert outlets[2].updated == 1
    assert device.closed == 1


def test_python_transport_rejects_alias_mismatch(monkeypatch):
    device = FakeDevice([
        FakeOutlet("Mac Mini"),
        FakeOutlet("ASIAIR"),
        FakeOutlet("Something Else"),
    ])
    install_fake_kasa(monkeypatch, device)

    transport = make_python_transport()

    with pytest.raises(KasaTransportError):
        transport.check_outlet(3, "Wave 150i")

    assert device.closed == 1


def test_python_transport_rejects_missing_outlet(monkeypatch):
    device = FakeDevice([
        FakeOutlet("Mac Mini"),
        FakeOutlet("ASIAIR"),
    ])
    install_fake_kasa(monkeypatch, device)

    transport = make_python_transport()

    with pytest.raises(KasaTransportError):
        transport.check_outlet(3, "Wave 150i")

    assert device.closed == 1


def test_python_transport_reports_on_and_off(monkeypatch):
    outlet = FakeOutlet("Wave 150i", is_on=True)
    device = FakeDevice([
        FakeOutlet("Mac Mini"),
        FakeOutlet("ASIAIR"),
        outlet,
    ])
    install_fake_kasa(monkeypatch, device)

    transport = make_python_transport()

    assert (
        transport.get_outlet_state(3, "Wave 150i")
        is SafetyPowerState.ON
    )

    outlet.is_on = False

    assert (
        transport.get_outlet_state(3, "Wave 150i")
        is SafetyPowerState.OFF
    )

    assert device.closed == 2


def test_python_transport_sends_off_only_after_validation(monkeypatch):
    outlet = FakeOutlet("Wave 150i", is_on=True)
    device = FakeDevice([
        FakeOutlet("Mac Mini"),
        FakeOutlet("ASIAIR"),
        outlet,
    ])
    install_fake_kasa(monkeypatch, device)

    # This unit test uses a fully fake Kasa device. Remove pytest's
    # runtime marker locally so the production hardware interlock does
    # not block the simulated turn_off() call.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    transport = make_python_transport()

    assert transport.power_off_outlet(3, "Wave 150i") is True
    assert outlet.turned_off == 1
    assert device.closed == 1


def test_python_transport_does_not_switch_wrong_alias(monkeypatch):
    outlet = FakeOutlet("Wrong Device", is_on=True)
    device = FakeDevice([
        FakeOutlet("Mac Mini"),
        FakeOutlet("ASIAIR"),
        outlet,
    ])
    install_fake_kasa(monkeypatch, device)

    transport = make_python_transport()

    with pytest.raises(KasaTransportError):
        transport.power_off_outlet(3, "Wave 150i")

    assert outlet.turned_off == 0
    assert device.closed == 1


def test_python_transport_wraps_connection_failure(monkeypatch):
    async def fake_connect_hs300(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(
        "modules.kasa_safety_power_adapter.connect_hs300",
        fake_connect_hs300,
    )

    transport = make_python_transport()

    with pytest.raises(KasaTransportError):
        transport.check_outlet(3, "Wave 150i")


from modules.guardian_types import (
    Capability,
    CapabilityStatus,
    SafetyPowerRole,
)
from modules.safety_power import SafetyPowerTopology
from modules.safety_power_capability_probe import (
    probe_safety_power_control,
)


def test_kasa_adapter_integrates_with_generic_safety_power_probe():
    adapter, transport = make_adapter()

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: SafetyPowerEndpoint(
                "pier-power",
                "asiair",
            ),
            SafetyPowerRole.MOUNT: SafetyPowerEndpoint(
                "pier-power",
                "mount",
            ),
        }
    )

    result = probe_safety_power_control(
        topology=topology,
        adapters={"pier-power": adapter},
    )

    assert result.capability is Capability.SAFETY_POWER_CONTROL
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.observation is True

    assert set(transport.checked) == {
        (2, "ASIAIR"),
        (3, "Wave 150i"),
    }

    assert transport.power_off_requests == []
