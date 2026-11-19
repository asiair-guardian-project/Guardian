from modules.wave_monitor import (
    WaveMonitorError,
    read_wave_status,
)


def main():
    print("Testing Wave 150i monitor")
    print()

    try:
        result = read_wave_status()

    except WaveMonitorError as error:
        print(f"RESULT: FAIL — {error}")
        return

    print(f"Reachable: {result['reachable']}")
    print()

    print("Axis 1")
    print(f"  Status:   {result['axis1']['status']}")
    print(f"  Position: {result['axis1']['position']}")
    print()

    print("Axis 2")
    print(f"  Status:   {result['axis2']['status']}")
    print(f"  Position: {result['axis2']['position']}")
    print()

    print("RESULT: PASS")


if __name__ == "__main__":
    main()