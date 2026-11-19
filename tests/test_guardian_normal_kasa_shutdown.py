import asyncio
from unittest.mock import patch

from modules.guardian import Guardian


class FakeGuardian(Guardian):
    def __init__(self):
        self.config = {
            "kasa": {
                "power_strip_ip": "192.0.2.10"
            }
        }


class FakeKasaController:
    last_targets = None

    def __init__(self, host):
        self.host = host

    async def power_off_emergency_targets(self, targets):
        FakeKasaController.last_targets = targets

        return {
            "verification": {
                "ASIAIR": {
                    "verified_off": True,
                },
                "Wave 150i": {
                    "verified_off": True,
                },
                "Pegasus": {
                    "verified_off": True,
                },
            }
        }


def test_normal_shutdown():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.KasaController",
        FakeKasaController,
    ):
        result = guardian.execute_kasa_normal_shutdown()

    assert result is True

    assert FakeKasaController.last_targets == [
        "ASIAIR",
        "WAVE",
        "PEGASUS",
    ]

    assert "Mac Mini" not in FakeKasaController.last_targets

    print(
        "PASS: normal shutdown targets only "
        "ASIAIR, Wave, and Pegasus"
    )


def main():
    print("Testing Guardian normal Kasa shutdown")
    print()

    test_normal_shutdown()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()