import re
import subprocess


class UPSStatusError(Exception):
    """Raised when UPS status cannot be determined safely."""


def read_ups_status():
    """
    Read UPS status from macOS using `pmset -g batt`.

    Returns a dictionary containing:
    - ups_present
    - power_source
    - battery_percent
    - state
    - runtime
    - raw_output
    """

    try:
        result = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise UPSStatusError(
            f"Unable to read UPS status: {error}"
        ) from error

    output = result.stdout.strip()

    if not output:
        raise UPSStatusError("pmset returned no UPS information.")

    ups_present = "CP1350PFCLCDa" in output

    if not ups_present:
        raise UPSStatusError(
            "CyberPower UPS was not detected."
        )

    if "Now drawing from 'UPS Power'" in output:
        power_source = "UPS"
    elif "Now drawing from 'AC Power'" in output:
        power_source = "AC"
    else:
        power_source = "UNKNOWN"

    percent_match = re.search(r"(\d+)%", output)

    if not percent_match:
        raise UPSStatusError(
            "Unable to determine UPS battery percentage."
        )

    battery_percent = int(percent_match.group(1))

    if "discharging" in output:
        state = "DISCHARGING"
    elif "charging" in output:
        state = "CHARGING"
    elif "not charging" in output:
        state = "NOT_CHARGING"
    else:
        state = "UNKNOWN"

    runtime_match = re.search(
        r"(\d+:\d+)\s+remaining",
        output,
    )

    runtime = (
        runtime_match.group(1)
        if runtime_match
        else None
    )

    return {
        "ups_present": True,
        "power_source": power_source,
        "battery_percent": battery_percent,
        "state": state,
        "runtime": runtime,
        "raw_output": output,
    }