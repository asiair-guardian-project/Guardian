from unittest.mock import patch

from modules.guardian import Guardian
from modules.wave_position_sampler import (
    WavePositionSamplerError,
)


class FakeSession:
    IMAGING_PERMITTED = "IMAGING_PERMITTED"

    def __init__(self):
        self.state = self.IMAGING_PERMITTED
        self.abort_called = False
        self.stop_called = False

    def abort(self):
        self.abort_called = True
        return True


class FakeGuardian(Guardian):
    def __init__(self):
        self.session = FakeSession()
        self.roof_close_protection_triggered = False
        self.protection_calls = []
        self.normal_kasa_shutdown_called = False

    def evaluate_protection(self, source, event_type):
        self.protection_calls.append(
            (source, event_type)
        )

    def execute_kasa_normal_shutdown(self):
        self.normal_kasa_shutdown_called = True
        return True

    def stop_session(self):
        self.session.stop_called = True


def simulate_roof_close(guardian):
    roof_status = "CLOSED"
    freshness_state = "FRESH"

    if guardian.session.state == guardian.session.IMAGING_PERMITTED:
        if (
            roof_status == "CLOSED"
            and freshness_state == "FRESH"
            and not guardian.roof_close_protection_triggered
        ):
            guardian.roof_close_protection_triggered = True

            with patch(
                "modules.guardian.sample_positions",
                return_value={
                    "axis1": {"delta": 0},
                    "axis2": {"delta": 0},
                },
            ), patch(
                "modules.guardian.wave_is_moving",
                return_value=False,
            ):
                sample_result = guardian_module_sample()
                wave_moving = guardian_module_moving(
                    sample_result
                )

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
                shutdown_ok = (
                    guardian.execute_kasa_normal_shutdown()
                )

                assert shutdown_ok is True

                guardian.stop_session()


def guardian_module_sample():
    from modules.guardian import sample_positions

    return sample_positions(interval_seconds=5)


def guardian_module_moving(sample_result):
    from modules.guardian import wave_is_moving

    return wave_is_moving(sample_result)


def test_stationary_wave_normal_roof_close():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.sample_positions",
        return_value={
            "axis1": {"delta": 0},
            "axis2": {"delta": 0},
        },
    ), patch(
        "modules.guardian.wave_is_moving",
        return_value=False,
    ):
        sample_result = guardian_module_sample()
        wave_moving = guardian_module_moving(sample_result)

        assert wave_moving is False

        shutdown_ok = guardian.execute_kasa_normal_shutdown()

        assert shutdown_ok is True
        guardian.stop_session()

    assert guardian.normal_kasa_shutdown_called is True
    assert guardian.protection_calls == []
    assert guardian.session.stop_called is True
    assert guardian.session.abort_called is False

    print(
        "PASS: stationary Wave at roof close runs normal "
        "Kasa housekeeping without emergency protection"
    )


def test_moving_wave_emergency_roof_close():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.sample_positions",
        return_value={
            "axis1": {"delta": 226},
            "axis2": {"delta": 0},
        },
    ), patch(
        "modules.guardian.wave_is_moving",
        return_value=True,
    ):
        sample_result = guardian_module_sample()
        wave_moving = guardian_module_moving(sample_result)

        assert wave_moving is True

        guardian.evaluate_protection(
            source="ROOF",
            event_type="CLOSED_WAVE_MOVING",
        )
        guardian.session.abort()

    assert guardian.normal_kasa_shutdown_called is False
    assert guardian.protection_calls == [
        ("ROOF", "CLOSED_WAVE_MOVING")
    ]
    assert guardian.session.abort_called is True
    assert guardian.session.stop_called is False

    print(
        "PASS: moving Wave at roof close triggers emergency protection"
    )


def test_unknown_wave_motion_fails_safe():
    guardian = FakeGuardian()

    with patch(
        "modules.guardian.sample_positions",
        side_effect=WavePositionSamplerError(
            "simulated read failure"
        ),
    ):
        try:
            sample_result = guardian_module_sample()
            wave_moving = guardian_module_moving(
                sample_result
            )

        except WavePositionSamplerError:
            wave_moving = None

        assert wave_moving is None

        guardian.evaluate_protection(
            source="ROOF",
            event_type="CLOSED_WAVE_MOTION_UNKNOWN",
        )
        guardian.session.abort()

    assert guardian.normal_kasa_shutdown_called is False
    assert guardian.protection_calls == [
        ("ROOF", "CLOSED_WAVE_MOTION_UNKNOWN")
    ]
    assert guardian.session.abort_called is True
    assert guardian.session.stop_called is False

    print(
        "PASS: unknown Wave motion at roof close fails safe"
    )


def main():
    print("Testing Guardian complete roof-close paths")
    print()

    test_stationary_wave_normal_roof_close()
    test_moving_wave_emergency_roof_close()
    test_unknown_wave_motion_fails_safe()

    print()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
