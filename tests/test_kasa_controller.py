import asyncio

from modules.kasa_controller import (
    KasaController,
    KasaControllerError,
)


async def main():
    controller = KasaController(
        host="192.168.1.112"
    )

    print("Testing HS300 read-only controller")
    print()

    try:
        outlets = await controller.get_outlets()

    except KasaControllerError as error:
        print(f"RESULT: FAIL — {error}")
        return

    for outlet in outlets:
        protection = (
            "PROTECTED"
            if outlet["protected"]
            else "controllable"
        )

        state = (
            "ON"
            if outlet["is_on"]
            else "OFF"
        )

        print(
            f"Outlet {outlet['number']}: "
            f"{outlet['name']} | "
            f"{state} | "
            f"{protection}"
        )

    print()
    print("RESULT: PASS")


asyncio.run(main())