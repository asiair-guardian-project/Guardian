import time


class MonitorLoop:
    """Runs Guardian monitoring cycles."""

    def __init__(self, guardian):
        self.guardian = guardian
        self.interval_seconds = (
            guardian.config["monitor"]["interval_seconds"]
        )

    def run(self, cycles=None):
        """
        Run Guardian monitoring.

        If cycles is an integer, run that many cycles.
        If cycles is None, run continuously until interrupted.
        """

        self.guardian.start()

        print("\nStarting monitor loop...\n")

        cycle = 0

        try:
            while True:
                cycle += 1

                self.guardian.monitor_once()

                if cycles is not None and cycle >= cycles:
                    break

                time.sleep(self.interval_seconds)

        except KeyboardInterrupt:
            print("\nGuardian monitoring interrupted by operator.")

        print("\nMonitor loop finished.")