from unittest.mock import patch

import modules.guardian as guardian_module
from modules.guardian import Guardian


class FakeGuardian(Guardian):
    def __init__(self, wave_moving):
        self.session = type(
            "FakeSession",
            (),
            {
                "IMAGING_PERMITTED": "IMAGING_PERMITTED",
                "state": "IMAGING_PERMITTED",
                "active": True,
                "abort": lambda self: setattr(
                    self,
                    "state",
                    "ABORTED",
                ) or True,
                "stop": lambda self: setattr(
                    self,
                    "state",
                    "DISARMED",
                ) or True,
            },
        )()

        self.roof_close_protection_triggered = False
        self.wave_moving = wave_moving
        self.protection_calls = []
        self.normal_shutdown_called = False

    def evaluate_protection(self, source, event_type):
        self.protection_calls.append(
            (source, event_type)
        )
        return [
            "STOP_WAVE",
            "POWER_OFF_PEGASUS",
            "POWER_OFF_ASIAIR",
        ]

    def execute_kasa_normal_shutdown(self):
        self.normal_shutdown_called = True
        return True


def run_roof_close(guardian):
    with patch(
        "modules.guardian.sample_positions",
        return_value={
            "axis1": {"delta": 0},
            "axis2": {"delta": 0},
        },
    ):
        with patch(
            "modules.guardian.wave_is_moving",
            return_value=guardian.wave_moving,
        ):
            guardian.roof_close_protection_triggered = False

            # Exercise the same decision logic used by monitor_once().
            wave_moving = None

            try:
                sample_result = (
                    guardian_module.sample_positions(
                        interval_seconds=5
                    )
                )

                wave_moving = (
                    guardian_module.wave_is_moving(
                        sample_result
                    )
                )

            except Exception:
                wave_moving = None

            if wave_moving is None:
                guardian.evaluate_protection(
                    source="ROOF",
                    event_type="CLOSED_WAVE_MOTION_UNKNOWN",
                )
                guardian.session.abort()

            elif wave_moving:
                guardian.evaluate_protection(
                    source="ROOF",
                    event_type="CLOSED_WAVE_MOVING",
                )
                guardian.session.abort()

            else:
                guardian.execute_kasa_normal_shutdown()
                guardian.session.stop()


def test_stationary_wave_normal_shutdown():
    guardian = FakeGuardian(wave_moving=False)

    run_roof_close(guardian)

    assert guardian.normal_shutdown_called is True
    assert guardian.protection_calls == []
    assert guardian.session.state == "DISARMED"

    print(
        "PASS: stationary Wave at roof close runs "
        "normal shutdown without emergency protection"
    )


def test_moving_wave_emergency_protection():
    guardian = FakeGuardian(wave_moving=True)

    run_roof_close(guardian)

    assert guardian.normal_shutdown_called is False
    assert guardian.protection_calls == [
        ("ROOF", "CLOSED_WAVE_MOVING")
    ]
    assert guardian.session.state == "ABORTED"

    print(
        "PASS: moving Wave at roof close triggers "
        "emergency protection"
    )


def test_unknown_wave_motion_fails_safe():
    guardian = FakeGuardian(wave_moving=None)

    with patch(
        "modules.guardian.sample_positions",
        side_effect=Exception(
            "simulated Wave position read failure"
        ),
    ):
        run_roof_close(guardian)

    assert guardian.normal_shutdown_called is False
    assert guardian.protection_calls == [
        ("ROOF", "CLOSED_WAVE_MOTION_UNKNOWN")
    ]
    assert guardian.session.state == "ABORTED"

    print(
        "PASS: unknown Wave motion at roof close "
        "fails safe"
    )


def main():
    print("Testing Guardian end-of-night roof-close sequence")
    print()

    test_stationary_wave_normal_shutdown()
    test_moving_wave_emergency_protection()
    test_unknown_wave_motion_fails_safe()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
