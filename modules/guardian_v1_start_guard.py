"""Stop Guardian v0.6 from starting while Guardian 1.0 is armed and able to cut power.

Two supervisors that can both cut power must never be live together. v1.0
already refuses to ARM while v0.6 runs; this closes the other direction
(v0.6 started after v1.0 is armed).

FAIL OPEN, on purpose: v0.6 is the live protection until Stage B. If anything
is uncertain (no socket, v1.0 not running, odd reply, any error) this returns
None and v0.6 starts normally. It blocks only on a clear answer from v1.0:
armed AND hardware execution enabled.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

DEFAULT_SOCKET = (
    Path.home() / "Library" / "Application Support" / "GuardianV1" / "operator.sock"
)
TIMEOUT_SECONDS = 1.0
MAX_REPLY_BYTES = 65536


def ask_status(socket_path, timeout):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        client.sendall(json.dumps({"command": "STATUS"}).encode("utf-8") + b"\n")
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
    finally:
        client.close()


def v1_blocks_start(socket_path=None, timeout=TIMEOUT_SECONDS):
    """Return a reason string if v0.6 must not start, else None. Never raises."""

    try:
        reply = ask_status(socket_path or DEFAULT_SOCKET, timeout)
        if reply is None or reply.get("code") != "STATUS":
            return None
        if reply.get("armed") is True and reply.get("hardware_execution_enabled") is True:
            return (
                "Guardian 1.0 is ARMED and able to cut power. Guardian v0.6 will not "
                "start while it is. DISARM Guardian 1.0 first, or run the Stage B "
                "rollback."
            )
        return None
    except Exception:
        return None
