#!/usr/bin/env python3
"""Start the Guardian v1.0 web page (read-only). Open http://127.0.0.1:8765 on this Mac;
add --tailscale-address to also reach it from your other Tailscale devices."""
import argparse
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modules.guardian_v1_tailscale import (  # noqa: E402
    TailscaleWatcher, find_tailscale_address)
from modules.guardian_v1_web import (  # noqa: E402
    DEFAULT_PORT, make_server, make_tailscale_server)

DEFAULT_SOCKET = Path.home() / "Library" / "Application Support" / "GuardianV1" / "operator.sock"


def say(*parts):
    print(*parts, flush=True)  # reliable in terminals and launchd logs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-socket", default=str(DEFAULT_SOCKET))
    parser.add_argument("--log-dir", default=str(Path(__file__).resolve().parent / "logs"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tailscale-address", default=None,
                        help="also listen on this Tailscale address (100.64.0.0/10 only), "
                             "or 'auto' to find it and keep checking until Tailscale is up")
    parser.add_argument("--allow-host", action="append", default=[],
                        help="a Tailscale host name you will type in the browser (repeatable)")
    return parser.parse_args(argv)


def start_servers(args, say=say):
    """Create the loopback server and, if asked and possible, the Tailscale one.

    Returns the list of servers (loopback first). A Tailscale address that is
    invalid or cannot be used never stops the page: it is reported and skipped.
    """
    server = make_server(args.operator_socket, args.log_dir, args.port)
    servers = [server]
    say(f"Guardian web page (read-only): http://127.0.0.1:{server.server_address[1]}")
    if args.tailscale_address == "auto":
        pass  # the watcher in main() finds the address and keeps checking
    elif args.tailscale_address:
        try:
            remote = make_tailscale_server(args.operator_socket, args.log_dir,
                                           args.tailscale_address, args.port, args.allow_host)
        except (ValueError, OSError) as error:
            say(f"NOT listening on Tailscale: {error}\nContinuing on 127.0.0.1 only.")
        else:
            servers.append(remote)
            say(f"  and over Tailscale:      http://{args.tailscale_address}:{remote.server_address[1]}")
            for name in args.allow_host:
                say(f"                           http://{name}:{remote.server_address[1]}")
    say("(Ctrl-C to stop)")
    return servers


def make_watcher(args, say=say, detect=find_tailscale_address):
    """The 'auto' Tailscale watcher, or None when --tailscale-address is not 'auto'."""
    if args.tailscale_address != "auto":
        return None

    def start(address):
        server = make_tailscale_server(args.operator_socket, args.log_dir,
                                       address, args.port, args.allow_host)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    return TailscaleWatcher(detect=detect, start=start, say=say)


def main(argv=None):
    args = parse_args(argv)
    servers = start_servers(args)
    for extra in servers[1:]:
        threading.Thread(target=extra.serve_forever, daemon=True).start()
    watcher = make_watcher(args)
    stop = threading.Event()
    if watcher is not None:
        threading.Thread(target=watcher.run, args=(stop,), daemon=True).start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for each in servers + ([watcher.server] if watcher and watcher.server else []):
            each.server_close()


if __name__ == "__main__":
    main()
