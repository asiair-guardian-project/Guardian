"""One-connection emergency shutdown of the Kasa strip (no hardware, no network).

The fake strip below behaves like the real one in the way that matters: each
connection takes a snapshot of outlet state when it is opened, so a read on
the same connection that sent the OFF commands is stale. Only a fresh
connection sees the truth.
"""
import pytest

from modules.guardian_types import (
    SafetyPowerResult, SafetyPowerRole, SafetyPowerState,
)
import modules.kasa_safety_power_adapter as adapter_module
from modules.guardian_v1_starfront_kasa import compose_starfront_kasa
from modules.kasa_safety_power_adapter import PythonKasaTransport

ALIASES = {1: "Mac Mini", 2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus",
           5: "spare", 6: "Plug 6"}
ALL_ROLES = {SafetyPowerRole.ASIAIR, SafetyPowerRole.MOUNT,
             SafetyPowerRole.ACCESSORIES}


class FakeWorld:
    """The physical strip plus a log of everything done to it."""

    def __init__(self, aliases=None, fail_turn_off=(), connects_fail=False):
        self.aliases = dict(aliases or ALIASES)
        self.on = {n: True for n in self.aliases}
        self.fail_turn_off = set(fail_turn_off)
        self.connects_fail = connects_fail
        self.connections = 0
        self.closed = 0
        self.log = []  # ("off", outlet) in the order commands were sent


class FakeChild:
    def __init__(self, world, number, snapshot_on):
        self.world, self.number = world, number
        self.alias = world.aliases[number]
        self._snapshot_on = snapshot_on

    @property
    def is_on(self):
        return self._snapshot_on  # stale until a new connection is made

    async def update(self):
        pass  # the real strip does not refresh truth on the same session

    async def turn_off(self):
        if self.number in self.world.fail_turn_off:
            raise RuntimeError("strip refused")
        self.world.log.append(("off", self.number))
        self.world.on[self.number] = False


class FakeStrip:
    def __init__(self, world):
        self.children = [
            FakeChild(world, n, world.on[n]) for n in sorted(world.aliases)
        ]


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    return install(monkeypatch, FakeWorld())


def install(monkeypatch, world):
    async def fake_connect(host, username, password, *, timeout_seconds=5):
        world.connections += 1
        if world.connects_fail:
            raise ConnectionError("unreachable")
        return FakeStrip(world)

    async def fake_close(strip):
        world.closed += 1

    monkeypatch.setattr(adapter_module, "connect_hs300", fake_connect)
    monkeypatch.setattr(adapter_module, "close_hs300", fake_close)
    return world


def wiring():
    transport = PythonKasaTransport(host="x.invalid", username="u", password="p")
    return compose_starfront_kasa(host="x.invalid", transport=transport)


def test_three_outlets_cut_and_verified_with_two_connections(world):
    records = wiring().execute_safety_power(ALL_ROLES)

    assert {r.role: r.result for r in records} == {
        role: SafetyPowerResult.VERIFIED_OFF for role in ALL_ROLES
    }
    assert world.connections == 2  # was 6: one to command, one to verify
    assert world.closed == 2
    assert sorted(n for _, n in world.log) == [2, 3, 4]
    assert world.on[1] is True  # the Mac mini is never touched
    assert world.on[5] is True and world.on[6] is True


def test_verification_really_uses_a_fresh_connection(world):
    # If verification reused the command connection it would read the stale
    # snapshot (still ON) and wrongly report FAILED. Passing here proves the
    # second connection is what confirmed the outlets are off.
    records = wiring().execute_safety_power(ALL_ROLES)
    assert all(r.result is SafetyPowerResult.VERIFIED_OFF for r in records)
    assert world.connections == 2


def test_wrong_outlet_name_is_refused_and_does_not_block_the_others(monkeypatch):
    aliases = dict(ALIASES)
    aliases[3] = "Something Else"
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    world = install(monkeypatch, FakeWorld(aliases=aliases))

    records = wiring().execute_safety_power(ALL_ROLES)
    by_role = {r.role: r.result for r in records}

    assert by_role[SafetyPowerRole.MOUNT] is SafetyPowerResult.FAILED
    assert by_role[SafetyPowerRole.ASIAIR] is SafetyPowerResult.VERIFIED_OFF
    assert by_role[SafetyPowerRole.ACCESSORIES] is SafetyPowerResult.VERIFIED_OFF
    assert world.on[3] is True  # the mismatched outlet was never switched
    assert 3 not in [n for _, n in world.log]


def test_one_outlet_refusing_does_not_stop_the_others(monkeypatch):
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    world = install(monkeypatch, FakeWorld(fail_turn_off={2}))

    records = wiring().execute_safety_power(ALL_ROLES)
    by_role = {r.role: r.result for r in records}

    assert by_role[SafetyPowerRole.ASIAIR] is SafetyPowerResult.FAILED
    assert by_role[SafetyPowerRole.MOUNT] is SafetyPowerResult.VERIFIED_OFF
    assert by_role[SafetyPowerRole.ACCESSORIES] is SafetyPowerResult.VERIFIED_OFF


def test_unreachable_strip_reports_every_outlet_failed(monkeypatch):
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    world = install(monkeypatch, FakeWorld(connects_fail=True))

    records = wiring().execute_safety_power(ALL_ROLES)

    assert all(r.result is SafetyPowerResult.FAILED for r in records)
    assert world.log == []


def test_failed_outlet_is_not_reported_verified_even_if_it_reads_off(monkeypatch):
    # The command failed, but the outlet happens to be off already. Guardian
    # still reports FAILED for the command it could not send, matching the
    # one-at-a-time path (no command sent -> FAILED).
    monkeypatch.setenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", "YES_I_UNDERSTAND")
    world = FakeWorld(fail_turn_off={4})
    world.on[4] = False
    install(monkeypatch, world)

    records = wiring().execute_safety_power(ALL_ROLES)
    by_role = {r.role: r.result for r in records}

    assert by_role[SafetyPowerRole.ACCESSORIES] is SafetyPowerResult.FAILED


def test_command_order_follows_the_shutdown_ordering(world):
    from modules.guardian_v1_starfront_kasa import TARGETS
    from modules.safety_power import (
        SafetyPowerEndpoint, SafetyPowerEndpointRequirements,
        SafetyPowerResourceEffects, order_shutdown_endpoints_by_resources,
    )

    wiring().execute_safety_power(ALL_ROLES)

    endpoints = {SafetyPowerEndpoint("starfront_hs300", eid)
                 for eid, _, _ in TARGETS.values()}
    expected = order_shutdown_endpoints_by_resources(
        endpoints,
        {e: SafetyPowerEndpointRequirements(e, frozenset()) for e in endpoints},
        {e: SafetyPowerResourceEffects(e, frozenset()) for e in endpoints},
    )
    outlet_of = {eid: number for eid, number, _ in TARGETS.values()}
    assert [n for _, n in world.log] == [
        outlet_of[e.endpoint_id] for e in expected
    ]


def test_switching_is_still_blocked_during_tests_without_the_override(monkeypatch):
    monkeypatch.delenv("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS", raising=False)
    world = install(monkeypatch, FakeWorld())

    records = wiring().execute_safety_power(ALL_ROLES)

    assert all(r.result is SafetyPowerResult.FAILED for r in records)
    assert world.log == []
    assert all(world.on[n] for n in ALIASES)


class OneAtATimeTransport:
    """A transport with no batch methods keeps the old behaviour."""

    def __init__(self):
        self.commands, self.reads = [], []

    def check_outlet(self, number, alias):
        return True

    def get_outlet_state(self, number, alias):
        self.reads.append(number)
        return SafetyPowerState.OFF

    def power_off_outlet(self, number, alias):
        self.commands.append((number, alias))
        return True


def test_transport_without_batch_support_uses_the_old_path():
    fake = OneAtATimeTransport()
    wire = compose_starfront_kasa(host="x.invalid", transport=fake)

    records = wire.execute_safety_power(ALL_ROLES)

    assert set(fake.commands) == {(2, "ASIAIR"), (3, "Wave 150i"), (4, "Pegasus")}
    assert sorted(fake.reads) == [2, 3, 4]
    assert all(r.result is SafetyPowerResult.VERIFIED_OFF for r in records)
