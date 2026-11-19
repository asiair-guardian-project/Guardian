import modules.guardian as guardian_module
from modules.guardian import Guardian
from modules.wave_stop_controller import WaveStopError


def fake_stop_wave_safely():
    raise WaveStopError(
        "Simulated Wave stop verification failure."
    )


guardian_module.stop_wave_safely = fake_stop_wave_safely

guardian = Guardian()

print("Testing Guardian Wave STOP failure handling")
print()

result = guardian.execute_wave_stop()

print()
print(f"Result: {result}")