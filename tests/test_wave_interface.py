from modules.wave_interface import (
    WaveCommunicationError,
    WaveInterface,
)


def main():
    wave = WaveInterface()

    print("Testing Wave 150i read-only interface")
    print()

    try:
        for axis in (1, 2):
            print(f"Axis {axis}")

            version = wave.get_version(axis)
            print(f"  Version:  {version}")

            status = wave.get_status(axis)
            print(f"  Status:   {status}")

            position = wave.get_position(axis)
            print(f"  Position: {position}")

            print()

    except WaveCommunicationError as error:
        print(f"RESULT: FAIL — {error}")
        return

    print("RESULT: PASS")


if __name__ == "__main__":
    main()