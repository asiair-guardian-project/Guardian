"""Run a Guardian commissioning rehearsal (real power cut, simulated trigger)."""
import sys

from modules.guardian_v1_rehearsal_cli import main

if __name__ == "__main__":
    sys.exit(main())
