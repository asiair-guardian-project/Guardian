"""Guardian 1.0 ICMP ASIAIR monitoring adapter."""

import re
import subprocess


# macOS ping runs about one second longer than its own -W wait when nothing
# answers (measured 3.02 s for -W 2000), so the process needs real slack or an
# unanswered ping is misread as a broken probe.
PROCESS_SLACK_SECONDS = 4.0

_PING_STATS = re.compile(
    r"(\d+) packets transmitted, (\d+) (?:packets )?received"
)


class AsiairIcmpAdapter:
    """Observe ASIAIR reachability using an independent ICMP path."""

    def __init__(
        self,
        host: str,
        timeout_seconds: float = 2.0,
    ) -> None:
        if not host:
            raise ValueError("ASIAIR host is required")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._host = host
        self._timeout_seconds = timeout_seconds

    def is_reachable(self) -> bool:
        """Return reachability; raise if the monitoring mechanism fails."""

        try:
            result = subprocess.run(
                [
                    "ping",
                    "-c",
                    "1",
                    "-W",
                    str(int(self._timeout_seconds * 1000)),
                    self._host,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=self._timeout_seconds + PROCESS_SLACK_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                "ASIAIR reachability probe could not execute"
            ) from exc

        if result.returncode == 0:
            return True

        # Exit codes differ by platform: Linux uses 1 for "sent, no reply",
        # macOS uses 2. The statistics line is the same on both, so trust it:
        # packets were sent and none came back means unreachable.
        stats = _PING_STATS.search(getattr(result, "stdout", None) or "")

        if stats is not None:
            sent, received = int(stats.group(1)), int(stats.group(2))

            if sent > 0 and received == 0:
                return False

            raise RuntimeError(
                f"ASIAIR ping gave inconsistent results "
                f"(exit {result.returncode}, {received} of {sent} replies)"
            )

        if result.returncode == 1:
            return False

        raise RuntimeError(
            f"ASIAIR ping failed with return code {result.returncode}"
        )
