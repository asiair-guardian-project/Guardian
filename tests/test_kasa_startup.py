import asyncio

from modules.kasa_controller import KasaController


class FakeOutlet:
    def __init__(self, alias, is_on=False):
        self.alias = alias
        self.is_on = is_on
        self.turn_on_calls = 0

    async def update(self):
        return None

    async def turn_on(self):
        self.turn_on_calls += 1
        self.is_on = True


class FakeStrip:
    def __init__(self):
        self.children = [
            FakeOutlet("Mac Mini", True),
            FakeOutlet("ASIAIR", False),
            FakeOutlet("Wave 150i", False),
            FakeOutlet("Pegasus", False),
            FakeOutlet("spare", False),
            FakeOutlet("Plug 6", False),
        ]


class FakeKasaController(KasaController):
    def __init__(self):
        super().__init__("192.168.1.112")
        self.discovery_count = 0
        self.close_count = 0
        self.fake_strip = FakeStrip()

    async def _get_strip(self):
        self.discovery_count += 1
        return self.fake_strip

    async def _close_strip(self, strip):
        assert strip is self.fake_strip
        self.close_count += 1


async def _run_startup_test():
    controller = FakeKasaController()

    result = await controller.power_on_imaging_targets()

    assert controller.discovery_count == 2
    assert controller.close_count == 2

    assert controller.fake_strip.children[0].is_on is True
    assert controller.fake_strip.children[0].turn_on_calls == 0

    assert controller.fake_strip.children[3].turn_on_calls == 1
    assert controller.fake_strip.children[2].turn_on_calls == 1
    assert controller.fake_strip.children[1].turn_on_calls == 1

    assert (
        controller.fake_strip.children[3].is_on
        and controller.fake_strip.children[2].is_on
        and controller.fake_strip.children[1].is_on
    )

    verification = result["verification"]

    assert verification["Pegasus"]["verified_on"] is True
    assert verification["Wave 150i"]["verified_on"] is True
    assert verification["ASIAIR"]["verified_on"] is True


def test_kasa_shared_session_startup(monkeypatch):
    # This test uses only FakeKasaController/FakeStrip/FakeOutlet.
    # Remove pytest's runtime marker locally so the production hardware
    # interlock does not block simulated switching.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    asyncio.run(_run_startup_test())


async def main():
    print("Testing Kasa shared-session startup")
    await _run_startup_test()
    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
