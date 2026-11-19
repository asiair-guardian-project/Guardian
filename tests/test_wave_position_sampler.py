from modules.wave_position_sampler import (
    WavePositionSamplerError,
    sample_positions,
    wave_is_moving,
)


def main():
    print("Testing Wave position sampler")
    print()

    try:
        result = sample_positions(
            interval_seconds=5
        )

    except WavePositionSamplerError as error:
        print(f"RESULT: FAIL — {error}")
        return

    print(
        f"Interval: {result['interval_seconds']} seconds"
    )
    print()

    print("Axis 1")
    print(
        f"  Before raw: {result['axis1']['before_raw']}"
    )
    print(
        f"  After raw:  {result['axis1']['after_raw']}"
    )
    print(
        f"  Delta:      {result['axis1']['delta']}"
    )
    print()

    print("Axis 2")
    print(
        f"  Before raw: {result['axis2']['before_raw']}"
    )
    print(
        f"  After raw:  {result['axis2']['after_raw']}"
    )
    print(
        f"  Delta:      {result['axis2']['delta']}"
    )
    print()

    moving = wave_is_moving(result)

    print(
        f"Wave moving: {'YES' if moving else 'NO'}"
    )
    print()

    print("RESULT: PASS")


if __name__ == "__main__":
    main()