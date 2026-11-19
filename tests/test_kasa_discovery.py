import asyncio
import os

from kasa.discover import Discover


async def main():
    print("Searching for Kasa devices...\n")

    username = os.environ.get("KASA_USERNAME")
    password = os.environ.get("KASA_PASSWORD")

    devices = await Discover.discover(
        username=username,
        password=password,
    )

    if not devices:
        print("No Kasa devices found.")
        return

    for ip, device in devices.items():
        await device.update()

        print(f"IP Address : {ip}")
        print(f"Alias      : {device.alias}")
        print(f"Model      : {device.model}")

        children = getattr(device, "children", None)

        if children:
            print("Outlets:")

            for index, child in enumerate(children, start=1):
                await child.update()

                print(
                    f"  {index}: "
                    f"{child.alias} | "
                    f"{'ON' if child.is_on else 'OFF'}"
                )

        print("-" * 40)


asyncio.run(main())