# Patch 25 - read the web page from your other Tailscale devices

    python guardian_v1_web.py --tailscale-address 100.x.y.z [--allow-host mac-name]

The page still always listens on 127.0.0.1. With --tailscale-address it ALSO listens on that one address, so your other devices on the same Tailscale network can open it (http://100.x.y.z:8765, or http://mac-name:8765 if you gave --allow-host mac-name).

## Safety rules
- The address must be in the Tailscale range 100.64.0.0/10. 0.0.0.0, LAN, public and loopback addresses, host names, and IPv6 are refused.
- If the Tailscale address cannot be used (for example Tailscale is not running), the page prints why and keeps running on 127.0.0.1 only.
- Each server answers only to its own names: the loopback server to 127.0.0.1/localhost, the Tailscale server to its address and the --allow-host names (plain names only, always with its own port). Any other Host header gets 403.
- Still read-only: GET only, STATUS only, no buttons. Controls are not available over Tailscale.
- Traffic between your devices is already encrypted by Tailscale; the page itself is plain HTTP inside that tunnel.

## Tests
tests/test_guardian_v1_web.py now has 24 tests. Mutation-checked 5 ways (range check, public-server validation, host check, name validation, loopback server leaking Tailscale names). The real bind to a 100.x address could not be run in the build environment; the same server code is tested on loopback with the Tailscale name list.

## 25b - startup messages flush immediately
The page's startup messages are now flushed as they are printed (reliable in terminals and launchd logs). On the Mac the CLI fallback test saw empty output because stdout was block-buffered when piped; the test now forces a large output buffer, so it fails whenever the program does not flush.

## 25c - no reverse name lookup at startup
Python's standard web server does a reverse name lookup of its own address when it starts (socket.getfqdn). It is never used. On a Mac using Tailscale's name service it can take several seconds, which made the page start slowly and made the CLI test time out. The server now skips it. The CLI test now reads the real program's output with a forced large buffer and no fixed timer.

## 25d - the startup logic is testable without a second program
The CLI's startup is split into parse_args() and start_servers(args, say). The brittle test that ran a second Python process and read its output (it failed on the Mac although the real program worked) is replaced by direct tests: an invalid address falls back to loopback; a valid address that cannot be bound falls back; a usable address adds a second server and prints both URLs; startup messages are flushed. Mutation-checked 4 ways.
