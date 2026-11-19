import asyncio
from unittest.mock import AsyncMock, patch

from modules.kasa_controller import (
    KasaController,
    KasaControllerError,
)


class FakeDevice:
    pass


async def _test_transient_failure():
    controller = KasaController("192.168.1.30")
    fake_device = FakeDevice()

    connect = AsyncMock(
        side_effect=[
            Exception("Simulated transient authentication failure"),
            fake_device,
        ]
    )

    with (
        patch.object(
            controller,
            "_credentials",
            return_value=("test-user", "test-password"),
        ),
        patch(
            "modules.kasa_controller.connect_hs300",
            connect,
        ),
        patch(
            "modules.kasa_controller.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        strip = await controller._get_strip()

    assert connect.await_count == 2
    assert strip is fake_device

    print("PASS: transient Kasa failure recovered on retry")


async def _test_persistent_failure():
    controller = KasaController("192.168.1.30")

    connect = AsyncMock(
        side_effect=Exception(
            "Simulated persistent authentication failure"
        )
    )

    with (
        patch.object(
            controller,
            "_credentials",
            return_value=("test-user", "test-password"),
        ),
        patch(
            "modules.kasa_controller.connect_hs300",
            connect,
        ),
        patch(
            "modules.kasa_controller.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        try:
            await controller._get_strip()
        except KasaControllerError:
            pass
        else:
            raise AssertionError(
                "_get_strip() unexpectedly succeeded."
            )

    assert connect.await_count == 3

    print("PASS: persistent Kasa failure stops after 3 attempts")


def test_transient_failure():
    asyncio.run(_test_transient_failure())


def test_persistent_failure():
    asyncio.run(_test_persistent_failure())


async def main():
    print("Testing Kasa connection retry behavior")
    print()

    await _test_transient_failure()
    await _test_persistent_failure()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
