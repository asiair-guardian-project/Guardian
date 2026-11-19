# Patch 35: Digital Loggers power controllers (UNTESTED ON REAL HARDWARE)

Adds `power.type: digital_loggers_rest` beside `kasa_hs300`. The Starfront/Kasa path is unchanged.

## What it does
- New transport `modules/guardian_v1_dli_transport.py` with the same interface as the Kasa transport, so the same
  safety adapter, shutdown order (ASIAIR, mount, accessories), host-outlet guard and verification are used.
- Newer Digital Loggers models with the REST API only (firmware 1.7+, e.g. Web Power Switch Pro, EPCR 5/6/7, Pro10).
  Older Web Power Switch / EPCR II-III models are NOT supported (no REST API, so no outlet-name check).
- Outlet numbers in the config are the numbers printed on the unit (1-8); the API's zero-based index is handled inside.
- Before every power-off the controller's own name for the outlet must equal the configured name exactly.
- Verification reads `physical_state` (the relay), never the commanded state. A reply that is not exactly one
  true/false (or one name) is "unknown", never "off".
- Batch calls use one connection, outlets processed in order, one bad outlet never blocks the others.
- Optional `power.scheme` (http/https, default http) and `power.port`.
- Credentials: `DLI_USERNAME` / `DLI_PASSWORD`, or macOS Keychain items "Guardian Digital Loggers Username" /
  "Guardian Digital Loggers Password" (account `guardian`). Never in the config, never asked by the wizard.
- Wizard: a "Kind of power controller" choice; outlet numbers up to 8 for Digital Loggers; next steps say "untested".
- `guardian_v1_dli_probe.py --config FILE`: read-only (GET only) survey of all outlets and a match report against the
  mapping. Run it before relying on this.
- Switching a non-loopback address is blocked while pytest runs (like the Kasa transport).

## What is assumed, not verified (no real unit was available)
- Reply shapes: selector requests (`=N`) answer a JSON list with one value (name string, true/false).
- OFF is `PUT /restapi/relay/outlets/=N/state/` form `value=false` with `X-CSRF: x`, answering 200 or 204.
- Digest auth with MD5 or SHA-256, qop=auth. HTTPS uses normal certificate checking (self-signed units: use http).
Anything different fails closed: the outlet is reported unknown / not cut, never verified off.

## Limits
- Tested only against a simulated controller (tests/dli_fake.py). Each operator must run the probe and commission
  their own cuts. The outlet live test, evidence audit and rehearsal scripts are still Starfront/Kasa-specific.
- All three roles and a host outlet are required, as for Kasa.
