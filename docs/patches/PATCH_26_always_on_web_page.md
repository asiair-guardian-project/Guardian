# Patch 26 - the web page as an always-on launchd job, with automatic Tailscale detection

## --tailscale-address auto
The page finds this Mac's Tailscale address itself and keeps checking every 30 s until Tailscale is up (so it works after a reboot, when Tailscale connects later than the page starts). If the address changes, the Tailscale-side server moves to it and the old one is closed. Losing Tailscale later leaves the existing server in place. A bind failure is logged once per distinct error, not every 30 s.

Detection reads /sbin/ifconfig and accepts ONLY an IPv4 address in 100.64.0.0/10 on a `utun` interface. The same range is used by some internet providers on the ordinary network interface; such an address is never accepted. Any error in detection means "not found". The loopback server is unaffected by all of this.

## launchd job
    python guardian_v1_web_launchd.py --output ~/ObservatorySupervisor/launchd/org.guardian.v1.web.plist [--allow-host NAME] [--no-tailscale]
writes (never overwrites) a plist: label org.guardian.v1.web, RunAtLoad, KeepAlive, ThrottleInterval 10, absolute paths, logs in ~/Library/Application Support/GuardianV1/web_stdout.log and web_stderr.log. It only writes a file you can inspect; it never loads or starts anything.

## Includes Patches 25-25d
(web page over Tailscale, startup flush, no reverse name lookup, testable startup)

## Tests
tests/test_guardian_v1_tailscale.py (18). Mutation-checked 8 ways (interface check, range check, restart on same address, old server not closed, KeepAlive, relative paths, overwrite, auto watcher).
Not testable in the build environment: a real utun interface and a real launchd load; both are first exercised on the Mac.
