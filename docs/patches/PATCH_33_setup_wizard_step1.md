# Patch 33 - first-run setup wizard, step one (local-only web page)

## What it is
    .venv/bin/python guardian_v1_setup_web.py [--folder DIR] [--port N]
Start it when you want it, open the printed address (http://127.0.0.1:8766/) on the same computer, stop it with Ctrl-C.
Five short screens: before you start, ASIAIR, roof status, power strip, review. It writes ONE new file,
`config.guardian-candidate.yaml`, in the folder given at startup (default: the current folder).

## What it does
* ASIAIR: a ping check. Roof: reads the Alpaca safety monitor once and reports what it read (SAFE / NOT SAFE).
  Strip: a ping (see 33b below); no session is opened and no command is sent, so no outlet can change.
* Values are validated with the same rules as the Mac app's Setup screen.
* Defaults Starfront's public Alpaca host and port; the operator supplies their own device number and addresses.

## What it never does
* No ARM, DISARM, RELEASE_ABORT, power switching, or any call to the monitor. A test fails if the code mentions them.
* Never activates a configuration, never commissions, never overwrites a file (exclusive create, private mode 0600,
  symlinks refused, partial file removed on a failed write). The page cannot choose the folder.
* Listens on 127.0.0.1 only; Host header checked; every POST needs a per-run token header and a JSON body; bodies are
  size-capped; a strict content policy; nothing is loaded from other sites.

## Not in this step (decided: later, separately)
* Letting an operator map their own outlets to roles. v1.0 still cuts only the fixed Starfront layout
  (outlets 2, 3, 4; never outlet 1). Digital Loggers and Eagle strips have no adapter yet.
* Listing the strip's outlets, activation, commissioning sign-off, Windows testing (the ASIAIR ping check uses the Mac
  ping command and has not been tried on Windows).
* The live monitor is untouched; nothing here changes how Guardian cuts power.

## Tests
tests/test_guardian_v1_setup_wizard.py (35): form validation, each check (including "sends nothing"), the single write,
the local-only page and its refusals, a static check that the code cannot arm or switch power, a check that no button
resolves to a browser built-in, and a real-Chrome run of the whole flow (skipped where there is no Chrome, such as the Mac).
Mutation-checked 12 ways. The browser run found and fixed a real bug: a button named write() called document.write().

## 33b (2026-11-18): the strip check is a ping
The first version connected to port 9999 on the strip. On the real strip that was refused (the HS300 here is reached
over authenticated KLAP, an HTTP-based protocol with an account sign-in, not port 9999). The check was based on an
assumption that was never verified against how Guardian itself connects. It is now a plain ping: it works on any strip,
opens no session, and sends nothing. Confirming the strip really is an HS300 and listing its outlets needs the Kasa sign-in
and is a later step. The Kasa sign-in is read by Guardian from the macOS Keychain; this page never asks for or stores it.

## 33c (2026-11-18): real-Mac walkthrough
All three checks passed against the live equipment. The wizard's file matched the live installation exactly for asiair, kasa and
monitor, and for roof except `status_file`. The live config.yaml is SHARED with other parts of Guardian (control, guardian, network,
notifications, session, system, wave), which the wizard's file does not contain. The final screen now warns never to copy the
wizard's file over an existing configuration; it is for a fresh install.
