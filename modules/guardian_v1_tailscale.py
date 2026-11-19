"""Find this Mac's Tailscale address, and keep the web page reachable on it.

Detection reads `ifconfig` and accepts ONLY an address in Tailscale's range
(100.64.0.0/10) that sits on a `utun` interface, which is where Tailscale puts
it. The same 100.x range is also used by some internet providers on the
ordinary network interface; such an address is never accepted, so the page
cannot be put on a provider-side network by mistake.
"""
import ipaddress
import subprocess

from modules.guardian_v1_web import validate_tailscale_address

IFCONFIG = "/sbin/ifconfig"
CHECK_INTERVAL_SECONDS = 30.0


def parse_tailscale_address(ifconfig_text):
    """The Tailscale IPv4 address found in `ifconfig` output, or None."""
    interface = None
    for line in str(ifconfig_text).splitlines():
        if line and not line[0].isspace():
            interface = line.split(":", 1)[0].strip()
            continue
        parts = line.split()
        if (interface and interface.startswith("utun")
                and len(parts) >= 2 and parts[0] == "inet"):
            try:
                return validate_tailscale_address(parts[1])
            except ValueError:
                continue
    return None


def find_tailscale_address(run=subprocess.run):
    """Run ifconfig and return the Tailscale address, or None. Never raises."""
    try:
        result = run([IFCONFIG], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    return parse_tailscale_address(result.stdout)


class TailscaleWatcher:
    """Starts the Tailscale-side server when an address appears, and moves it if it changes.

    `start(address)` must return a server that is already serving; `stop` is
    called on the old server when the address changes. Nothing here can stop
    the loopback server or the page.
    """

    def __init__(self, *, detect, start, say, stop=None):
        self.detect, self.start, self.say = detect, start, say
        self.stop = stop or (lambda server: server.shutdown() or server.server_close())
        self.address = None
        self.server = None
        self._waiting_said = False
        self._last_failure = None

    def check_once(self):
        try:
            address = self.detect()
        except Exception:
            address = None
        if address is None:
            if self.server is None and not self._waiting_said:
                self.say("Tailscale not found yet; will keep checking every "
                         f"{int(CHECK_INTERVAL_SECONDS)} s.")
                self._waiting_said = True
            return
        if address == self.address:
            return
        old = self.server
        try:
            server = self.start(address)
        except (ValueError, OSError) as error:
            failure = (address, str(error))
            if failure != self._last_failure:  # say it once, not every 30 s
                self.say(f"Could not listen on Tailscale address {address}: {error}")
                self._last_failure = failure
            self._waiting_said = True
            return
        self.server, self.address = server, address
        self._waiting_said = False
        self._last_failure = None
        if old is not None:
            try:
                self.stop(old)
            except Exception:
                pass
            self.say(f"Tailscale address changed to {address}.")
        self.say(f"  over Tailscale:          http://{address}:{server.server_address[1]}")

    def run(self, stop_event):
        while not stop_event.is_set():
            self.check_once()
            stop_event.wait(CHECK_INTERVAL_SECONDS)
