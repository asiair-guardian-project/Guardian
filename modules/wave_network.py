import subprocess
import time

from modules.wave_monitor import (
    WaveMonitorError,
    read_wave_status,
)


WIFI_INTERFACE = "en1"
WAVE_SSID = "SynScan_5d15"


class WaveNetworkError(Exception):
    """Raised when Wave Wi-Fi recovery fails unexpectedly."""


def wave_reachable():
    """Return True if Guardian can communicate with the Wave."""

    try:
        read_wave_status()
    except WaveMonitorError:
        return False

    return True


def attempt_wave_wifi_join():
    """
    Ask macOS to join the Wave Wi-Fi network.

    This does not send any command to the mount itself.
    """

    result = subprocess.run(
        [
            "networksetup",
            "-setairportnetwork",
            WIFI_INTERFACE,
            WAVE_SSID,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    return result.returncode == 0


def ensure_wave_connection(wait_seconds=15, poll_interval=1):
    """
    Ensure Guardian has a working communication path to the Wave.

    Returns:
        "ONLINE"    - Wave was already reachable.
        "RECOVERED" - Wi-Fi join restored Wave communication.
        "OFFLINE"   - Wave could not be reached within the recovery window.
    """

    if wave_reachable():
        return "ONLINE"

    if not attempt_wave_wifi_join():
        return "OFFLINE"

    deadline = time.monotonic() + wait_seconds

    while time.monotonic() < deadline:
        time.sleep(poll_interval)

        if wave_reachable():
            return "RECOVERED"

    return "OFFLINE"

def get_wave_network_diagnostics():
    """
    Capture Mac-side network state for the Wave communication path.

    Returns a dictionary containing:
        en1_ip          - IPv4 address currently assigned to en1, or None
        route_interface - interface used to reach the Wave, or None
        ping_ok         - whether the Wave hotspot answers one ping
    """

    diagnostics = {
        "en1_ip": None,
        "route_interface": None,
        "ping_ok": False,
    }

    ip_result = subprocess.run(
        ["ipconfig", "getifaddr", WIFI_INTERFACE],
        capture_output=True,
        text=True,
        check=False,
    )

    if ip_result.returncode == 0:
        value = ip_result.stdout.strip()
        if value:
            diagnostics["en1_ip"] = value

    route_result = subprocess.run(
        ["route", "-n", "get", "192.168.4.1"],
        capture_output=True,
        text=True,
        check=False,
    )

    if route_result.returncode == 0:
        for line in route_result.stdout.splitlines():
            if line.strip().startswith("interface:"):
                diagnostics["route_interface"] = (
                    line.split(":", 1)[1].strip()
                )
                break

    ping_result = subprocess.run(
        ["ping", "-c", "1", "-W", "1000", "192.168.4.1"],
        capture_output=True,
        text=True,
        check=False,
    )

    diagnostics["ping_ok"] = ping_result.returncode == 0

    return diagnostics
