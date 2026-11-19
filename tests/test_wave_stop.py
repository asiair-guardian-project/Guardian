import time

from modules.wave_interface import (
    WaveCommunicationError,
    WaveInterface,
)


def main():
    wave = WaveInterface()

    print("Wave 150i controlled STOP test")
    print("This test issues STOP commands only.")
    print()

    try:
        for axis in (1, 2):
            print(f"Axis {axis}")

            position_before = wave.get_position(axis)
            print(f"  Position before: {position_before}")

            time.sleep(2)

            position_check = wave.get_position(axis)
            print(f"  Position check:  {position_check}")

            if position_before != position_check:
                print("  RESULT: ABORT — axis position changed.")
                print("  STOP command was not issued.")
                return

            print("  Axis appears stationary.")

            response = wave.stop(axis)
            print(f"  STOP response:   {response}")

            time.sleep(2)

            position_after = wave.get_position(axis)
            print(f"  Position after:  {position_after}")

            if position_check != position_after:
                print("  RESULT: FAIL — position changed after STOP.")
                return

            print("  RESULT: PASS")
            print()

    except WaveCommunicationError as error:
        print(f"RESULT: FAIL — {error}")
        return

    print("ALL AXES: PASS")


if __name__ == "__main__":
    main()