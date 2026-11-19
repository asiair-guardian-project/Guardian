import urllib.error
import urllib.request


def internet_available(test_url, timeout_seconds=5):
    """Return True if the internet test URL is reachable."""

    try:
        with urllib.request.urlopen(
            test_url,
            timeout=timeout_seconds,
        ):
            return True

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ):
        return False