# Patch 14: spare the power strip

The HS300 does not tolerate closely spaced connections. Before this patch the armed monitor
opened one connection PER required outlet on EVERY 5-second cycle (two connections, about 1.3 s
each). Now:

* the health check reads both required outlets over ONE connection;
* it runs once a minute (`--strip-check-seconds`, default 60); the last good result stands in between;
* a failed check is retried on the next cycles (about 4-5 s apart) and the strip is only reported
  unavailable after THREE failures in a row, matching the three attempts v0.6 makes.

The emergency cut path (one connection to command, one fresh connection to verify) does not use
this schedule. The watch-only monitor does not read the strip at all. Do not use the watch tool's
`--kasa-host` option for long runs.
