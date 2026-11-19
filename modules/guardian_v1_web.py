"""Guardian v1.0 local web page (read-only first version).

A SEPARATE program from the monitor. It never touches hardware and never runs
inside the monitor: it asks the monitor's existing local operator socket for
STATUS, reads the v1.0 event log, and serves a small page. If this program
dies or hangs, protection is unaffected.

Safety rules in this version:
  * always listens on 127.0.0.1; it can ALSO listen on one Tailscale address
    (100.64.0.0/10, validated), never on 0.0.0.0, a LAN or a public address;
  * the Host header must be one of that server's own names with its own port,
    which blocks DNS-rebinding from a web page in the browser;
  * GET only; no command of any kind is forwarded to the monitor except STATUS;
  * the incident token and file paths in the monitor's reply are NOT passed on;
  * a monitor that cannot be reached is shown as "no contact", never as fine.
"""
import ipaddress
import json
import os
import re
import socket
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from modules.guardian_v1_night_summary import read_events, render, summarize

DEFAULT_PORT = 8765
SOCKET_TIMEOUT_SECONDS = 2.0
MAX_REPLY_BYTES = 65536
EVENT_LINES = 40
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Only these fields of the monitor's STATUS reply reach the browser.
STATUS_FIELDS = (
    "session", "armed", "arm_available", "arm_unavailable_reason",
    "hardware_execution_enabled", "recovery_reason", "arm_blocked",
    "incident_active", "acknowledged", "unresolved_actions", "equipment",
)
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"),
}


TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
HOST_NAME = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


def validate_tailscale_address(text):
    """Return the address as text if it is an IPv4 address in the Tailscale range."""
    try:
        address = ipaddress.ip_address(str(text).strip())
    except ValueError:
        raise ValueError(f"Not an IP address: {text!r}") from None
    if address.version != 4 or address not in TAILSCALE_NET:
        raise ValueError(f"{address} is not a Tailscale address (100.64.0.0/10)")
    return str(address)


def validate_host_names(names):
    out = []
    for name in names:
        lowered = str(name).strip().lower()
        if not HOST_NAME.match(lowered):
            raise ValueError(f"Not a plain host name: {name!r}")
        out.append(lowered)
    return out


def ask_monitor(socket_path, request, timeout=SOCKET_TIMEOUT_SECONDS):
    """Send one request line to the monitor, return its reply dict or None."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        client.sendall(json.dumps(request).encode("utf-8") + b"\n")
        data = b""
        while b"\n" not in data and len(data) <= MAX_REPLY_BYTES:
            part = client.recv(4096)
            if not part:
                break
            data += part
        if b"\n" not in data:
            return None
        reply = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
        return reply if isinstance(reply, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None
    finally:
        client.close()


def monitor_status(socket_path):
    reply = ask_monitor(socket_path, {"command": "STATUS"})
    if reply is None or reply.get("code") != "STATUS":
        return {"connected": False}
    status = {key: reply[key] for key in STATUS_FIELDS if key in reply}
    status["connected"] = True
    return status


def _tail_one(path, count):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 65536))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()][-count:]


def tail_lines(path, count=EVENT_LINES):
    """The last `count` log lines, reaching back into daily archives if the
    current file is short (it starts empty after each midnight rotation)."""
    path = Path(path)
    lines = _tail_one(path, count)
    if len(lines) >= count:
        return lines
    try:
        archives = sorted(path.parent.glob(path.name + ".*"), reverse=True)
    except OSError:
        archives = []
    for archive in archives:
        lines = _tail_one(archive, count - len(lines)) + lines
        if len(lines) >= count:
            break
    return lines


def make_handler(socket_path, log_dir):
    log_dir = Path(log_dir)

    class Handler(BaseHTTPRequestHandler):
        server_version = "GuardianWeb"
        sys_version = ""

        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _host_ok(self):
            return self.headers.get("Host", "").lower() in self.server.allowed_hosts

        def _send(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload):
            self._send(200, json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            path = self.path.split("?", 1)[0]
            if path in STATIC:
                name, kind = STATIC[path]
                try:
                    body = (WEB_DIR / name).read_bytes()
                except OSError:
                    return self._send(404, b"Not found", "text/plain; charset=utf-8")
                return self._send(200, body, kind)
            if path == "/api/status":
                return self._json(monitor_status(socket_path))
            if path == "/api/events":
                return self._json({"lines": tail_lines(log_dir / "guardian_v1.log")})
            if path == "/api/nights":
                return self._json({"text": render(
                    summarize(read_events(log_dir)), last=7)})
            return self._send(404, b"Not found", "text/plain; charset=utf-8")

        def _refuse(self):
            self._send(405, b"Read-only", "text/plain; charset=utf-8")

        do_POST = do_PUT = do_DELETE = do_PATCH = _refuse

    return Handler


class _Server(ThreadingHTTPServer):
    def server_bind(self):
        # The standard server also does a reverse name lookup of its own address
        # here (socket.getfqdn). It is never used, and on a Mac using Tailscale's
        # name service it can take seconds, so it is skipped.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def _serve(address, port, socket_path, log_dir, names):
    server = _Server((address, port), make_handler(socket_path, log_dir))
    server.daemon_threads = True
    bound = server.server_address[1]
    server.allowed_hosts = {f"{name}:{bound}" for name in names}
    return server


def make_server(socket_path, log_dir, port=DEFAULT_PORT):
    """The loopback server. There is deliberately no host parameter."""
    return _serve("127.0.0.1", port, socket_path, log_dir, ("127.0.0.1", "localhost"))


def make_tailscale_server(socket_path, log_dir, address, port=DEFAULT_PORT, allowed_names=()):
    """A second server on ONE Tailscale address; anything else is refused."""
    address = validate_tailscale_address(address)
    names = [address] + validate_host_names(allowed_names)
    return _serve(address, port, socket_path, log_dir, names)
