from modules.guardian import Guardian
from modules.protection_engine import ProtectionEngine


class FakeSession:
    def __init__(self):
        self.active = True


class FakeGuardian(Guardian):
    def __init__(self, wave_stop_success):
        self.session = FakeSession()
        self.protection = ProtectionEngine()
        self.protection_results = {}

        self.wave_stop_success = wave_stop_success
        self.wave_stop_called = False
        self.kasa_batch_calls = []

    def execute_wave_stop(self):
        self.wave_stop_called = True
        return self.wave_stop_success

    def execute_kasa_emergency_batch(self, targets):
        self.kasa_batch_calls.append(
            list(targets)
        )

        verification = {
            "ASIAIR": {
                "verified_off": True,
            },
            "Pegasus": {
                "verified_off": True,
            },
        }

        if "WAVE" in targets:
            verification["Wave 150i"] = {
                "verified_off": True,
            }

        return {
            "verification": verification
        }


def test_wave_stop_succeeds():
    guardian = FakeGuardian(
        wave_stop_success=True
    )

    actions = guardian.evaluate_protection(
        source="ASIAIR",
        event_type="OFFLINE",
    )

    assert guardian.wave_stop_called is True

    assert guardian.kasa_batch_calls == [
        [
            "WAVE",
            "PEGASUS",
            "ASIAIR",
        ]
    ]

    assert guardian.protection_results[
        "STOP_WAVE"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_PEGASUS"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_ASIAIR"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_WAVE"
    ] == "VERIFIED"

    assert "STOP_WAVE" in actions

    print(
        "PASS: successful controlled Wave STOP is followed by "
        "verified Wave, ASIAIR, and Pegasus power removal"
    )


def test_wave_stop_fails():
    guardian = FakeGuardian(
        wave_stop_success=False
    )

    actions = guardian.evaluate_protection(
        source="ASIAIR",
        event_type="OFFLINE",
    )

    assert guardian.wave_stop_called is True

    assert guardian.kasa_batch_calls == [
        [
            "WAVE",
            "PEGASUS",
            "ASIAIR",
        ]
    ]

    assert guardian.protection_results[
        "STOP_WAVE"
    ] == "FAILED"

    assert guardian.protection_results[
        "POWER_OFF_WAVE"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_PEGASUS"
    ] == "VERIFIED"

    assert guardian.protection_results[
        "POWER_OFF_ASIAIR"
    ] == "VERIFIED"

    assert "STOP_WAVE" in actions

    print(
        "PASS: failed controlled Wave STOP falls back "
        "to verified Wave Kasa power removal"
    )


def main():
    print(
        "Testing Guardian ASIAIR emergency sequence"
    )
    print()

    test_wave_stop_succeeds()
    test_wave_stop_fails()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()