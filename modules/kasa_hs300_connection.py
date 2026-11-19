"""Shared authenticated connection support for the observatory HS300."""

from kasa.iot.iotstrip import IotStrip
from kasa.protocols import IotProtocol
from kasa.transports.klaptransport import (
    Credentials,
    DeviceConfig,
    KlapTransportV2,
)


class KasaHS300ConnectionError(RuntimeError):
    """Raised when an authenticated HS300 connection cannot be established."""


async def connect_hs300(
    host: str,
    username: str,
    password: str,
    *,
    timeout_seconds: int = 5,
) -> IotStrip:
    """
    Return an authenticated HS300 represented explicitly as an IotStrip.

    python-kasa discovery can classify a KLAP-connected HS300 as an
    IotPlug, which hides the strip's physical child outlets. Guardian
    requires those outlets for physical-number and alias validation.
    """

    config = DeviceConfig(
        host=host,
        timeout=timeout_seconds,
        credentials=Credentials(
            username,
            password,
        ),
    )

    transport = KlapTransportV2(config=config)
    protocol = IotProtocol(transport=transport)

    strip = IotStrip(
        host,
        config=config,
        protocol=protocol,
    )

    try:
        await strip.update()

        if not strip.children:
            raise KasaHS300ConnectionError(
                "HS300 does not expose individual outlets."
            )

        return strip

    except Exception:
        await protocol.close()
        raise


async def close_hs300(strip: IotStrip) -> None:
    """Close the protocol and HTTP resources owned by an HS300 connection."""

    await strip.protocol.close()
