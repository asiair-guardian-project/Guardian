import argparse

from modules.guardian import Guardian
from modules.monitor_loop import MonitorLoop


def parse_args():
    parser = argparse.ArgumentParser(
        description="Guardian Observatory Supervisor"
    )

    parser.add_argument(
        "--armed",
        action="store_true",
        help="Start Guardian with protection armed.",
    )

    return parser.parse_args()


def _v1_start_block_reason():
    """Reason v0.6 must not start (Guardian 1.0 armed), else None. Fails open."""

    try:
        from modules.guardian_v1_start_guard import v1_blocks_start

        return v1_blocks_start()
    except Exception:
        return None


def main():
    args = parse_args()

    reason = _v1_start_block_reason()

    if reason:
        print(f"Guardian v0.6 not started: {reason}", flush=True)
        raise SystemExit(75)

    guardian = Guardian()

    # Restore persistent emergency state before accepting ARM.
    guardian.restore_emergency_state()

    if args.armed:
        guardian.start_session()

    loop = MonitorLoop(guardian)
    loop.run()


if __name__ == "__main__":
    main()