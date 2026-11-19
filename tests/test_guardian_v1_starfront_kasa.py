from modules.guardian_types import SafetyPowerRole, SafetyPowerState
from modules.guardian_v1_starfront_kasa import compose_starfront_kasa


class FakeTransport:
    def __init__(self):
        self.commands = []
    def check_outlet(self, number, alias):
        return True
    def get_outlet_state(self, number, alias):
        return SafetyPowerState.OFF
    def power_off_outlet(self, number, alias):
        self.commands.append((number, alias))
        return True


def test_three_roles_route_to_expected_outlets_only():
    fake = FakeTransport()
    wiring = compose_starfront_kasa(host="example.invalid", transport=fake)
    records = wiring.execute_safety_power({
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
        SafetyPowerRole.ACCESSORIES,
    })
    assert set(fake.commands) == {
        (2, "ASIAIR"), (3, "Wave 150i"), (4, "Pegasus")
    }
    assert len(records) == 3
    assert all(r.result.name == "VERIFIED_OFF" for r in records)
    assert all(number != 1 for number, _ in fake.commands)


def test_composition_does_not_issue_commands():
    fake = FakeTransport()
    compose_starfront_kasa(host="example.invalid", transport=fake)
    assert fake.commands == []
