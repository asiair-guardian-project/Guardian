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
    def __init__(self, host):
        self.host = host

    async def power_on_imaging_targets(self):
        return {
            "verification": {
                "ASIAIR": {
                    "verified_on": True,
                },
                "Wave 150i": {
                    "verified_on": True,
                },
                "Pegasus": {
                    "verified_on": True,
                },
            }
        }


class FakeFailedKasaController:
    def __init__(self, host):
        self.host = host

    async def power_on_imaging_targets(self):
        return {
            "verification": {
                "ASIAIR": {
                    "verified_on": True,
                },
                "Wave 150i": {
                    "verified_on": False,
                },
                "Pegasus": {
                    "verified_on": True,
                },
            }
        }


def test_imaging_startup():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.KasaController",
        FakeKasaController,
    ):
        result = guardian.execute_kasa_imaging_startup()

    assert result is True

    print(
        "PASS: imaging startup verifies "
        "ASIAIR, Wave, and Pegasus ON"
    )


def test_imaging_startup_verification_failure():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.KasaController",
        FakeFailedKasaController,
    ):
        result = guardian.execute_kasa_imaging_startup()

    assert result is False

    print(
        "PASS: startup fails when an imaging outlet "
        "cannot be verified ON"
    )


def main():
    print("Testing Guardian imaging Kasa startup")
    print()

    test_imaging_startup()
    test_imaging_startup_verification_failure()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()