import subprocess


def asiair_available(host, timeout_seconds=2):
    """Return True if the ASIAIR responds to ping."""

    result = subprocess.run(
        [
            "ping",
            "-c",
            "1",
            "-W",
            str(timeout_seconds * 1000),
            host,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return result.returncode == 0