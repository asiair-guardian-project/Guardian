from modules.wave_stop_controller import (
    WaveStopError,
    stop_wave_safely,
)


class FakeWave:
    """Fake Wave interface for software-only stop testing."""

    def __init__(self, axis1_positions, axis2_positions):
        self.positions = {
            1: list(axis1_positions),
            2: list(axis2_positions),
        }

        self.stop_calls = []

    def stop(self, axis):
        self.stop_calls.append(axis)
        return "="

    def get_position(self, axis):
        return self.positions[axis].pop(0)


print("CASE 1: Both axes stop successfully")

wave = FakeWave(
    axis1_positions=["=AAAAAA", "=AAAAAA"],
    axis2_positions=["=BBBBBB", "=BBBBBB"],
)

result = stop_wave_safely(
    wave=wave,
    verification_interval_seconds=0,
)

print(result)
print(f"STOP calls: {wave.stop_calls}")
print()


print("CASE 2: Axis 1 continues moving")

wave = FakeWave(
    axis1_positions=["=AAAAAA", "=AAAAAB"],
    axis2_positions=["=BBBBBB", "=BBBBBB"],
)

try:
    stop_wave_safely(
        wave=wave,
        verification_interval_seconds=0,
    )

except WaveStopError as error:
    print(f"SAFE FAILURE: {error}")

print(f"STOP calls: {wave.stop_calls}")