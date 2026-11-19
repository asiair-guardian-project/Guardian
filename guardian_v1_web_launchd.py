#!/usr/bin/env python3
"""Write a launchd plist that keeps the Guardian v1.0 web page running (read-only).

It only WRITES a file you can inspect; it never loads or starts anything.
    python guardian_v1_web_launchd.py --output ~/ObservatorySupervisor/launchd/org.guardian.v1.web.plist
"""
import argparse
import os
from pathlib import Path
import plistlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modules.guardian_v1_web import DEFAULT_PORT, validate_host_names  # noqa: E402

LABEL = "org.guardian.v1.web"
SUPPORT = Path.home() / "Library" / "Application Support" / "GuardianV1"


def build_plist(*, python, project, tailscale=True, allow_hosts=(), port=DEFAULT_PORT,
                support=SUPPORT):
    python, project, support = Path(python), Path(project), Path(support)
    for path in (python, project, support):
        if not path.is_absolute():
            raise ValueError(f"Path must be absolute: {path}")
    args = [str(python), str(project / "guardian_v1_web.py"),
            "--operator-socket", str(support / "operator.sock"),
            "--log-dir", str(project / "logs"),
            "--port", str(int(port))]
    if tailscale:
        args += ["--tailscale-address", "auto"]
    for name in validate_host_names(allow_hosts):
        args += ["--allow-host", name]
    return {
        "Label": LABEL,
        "ProgramArguments": args,
        "WorkingDirectory": str(project),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(support / "web_stdout.log"),
        "StandardErrorPath": str(support / "web_stderr.log"),
    }


def main(argv=None):
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new plist file to write (never overwritten)")
    parser.add_argument("--python", default=str(project / ".venv" / "bin" / "python"))
    parser.add_argument("--no-tailscale", action="store_true", help="loopback only")
    parser.add_argument("--allow-host", action="append", default=[])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    data = plistlib.dumps(build_plist(
        python=Path(args.python).expanduser().absolute(), project=project,
        tailscale=not args.no_tailscale, allow_hosts=args.allow_host, port=args.port))
    path = Path(args.output).expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
