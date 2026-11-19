# Guardian 1.0 operator guide (ASIAIR + Starfront Observatories)

Guardian 1.0 watches your observatory and cuts power to your equipment when it is no longer safe. It exists for rigs
that cannot protect themselves: with an ASIAIR you cannot pause imaging or shut down remotely without supervision, so
Guardian does the one thing that always works: it switches off the outlets.

**Read "What Guardian will and will not do" before anything else. Guardian is a safety aid you commission and supervise
yourself. It is not a guarantee.**

---

## What Guardian will and will not do

**It will**
- Watch the roof status (Starfront's Alpaca safety-monitor feed), the ASIAIR (is it answering?), the power controller,
  and a UPS if you have one.
- When an imaging session is running and the roof reads CLOSED, cut power to the ASIAIR, the mount and your accessories
  (in that order), then read each outlet back to confirm it is really off. It then disarms itself and latches an
  "aborted" state.
- Do the same if the ASIAIR is lost for two checks in a row (after it had been online), if a UPS reports low battery,
  or if Guardian itself hits an internal fault.
- Treat a roof feed that stays UNKNOWN as a problem: after 12 unknown readings over at least 60 seconds it cuts.
- Refuse to switch any outlet whose name on the controller does not exactly match the name you configured, and refuse
  to ever switch the outlet your Guardian computer is plugged into.

**It will not**
- Turn anything back on. After a cut you restore power yourself, then acknowledge the abort in the app.
- Park the mount, close the roof or stop an exposure. Cutting power is its only physical action.
- Work without you: it must be armed by you, and the computer running it must stay powered and online.
- Protect you from a failure it cannot see: a dead Guardian computer, an internet outage that also takes out the
  controller, an outlet that physically sticks on.
- Run on Windows, or with a roof source other than Starfront's Alpaca feed (today).

**Power controllers**: Kasa HS300 (tested on real hardware). Digital Loggers REST-API models (**NOT tested on real
hardware**; run `guardian_v1_dli_probe.py` first and treat it as experimental).

---

## What you need

- A Mac that is always on, on the same network as your ASIAIR and power controller, plugged into the controller's
  **own** outlet (Guardian never switches that outlet).
- Python 3 and this project folder (`~/ObservatorySupervisor`), with its virtual environment (`.venv`) and the packages
  in `requirements.txt` (including python-kasa; use the version pinned there).
- An ASIAIR at a fixed address; your Starfront Alpaca device number; a power controller with **all three** of ASIAIR,
  mount and accessories on separate outlets.
- Optional: a UPS Guardian can read.

---

## The Start Guardian icon (so you never have to hunt for the folder)

Once the project is installed, make a desktop icon with one command (run it from the project folder, one time):
`.venv/bin/python guardian_v1_launcher.py install`. That puts **Start Guardian.command** on your Desktop. If macOS
blocks it the first time, right-click it, choose **Open**, then **Open** again.

Double-click it whenever you come back after a long gap. It looks at where you are up to and does the next thing:
- no configuration yet: opens the setup page in your browser (leave its Terminal window open until you finish);
- a setup file is waiting: opens this guide so you can do the next step;
- configuration done but no app yet: builds the Guardian app, then opens it;
- app built: opens the Guardian app.

It never switches power, ARMs or changes your configuration. Steps 2 to 6 below (sign-in, outlet check, monitor,
commissioning) are still Terminal commands; the icon takes you to the beginning and to the app. If you move the
project folder, run the `install` command again. `.venv/bin/python guardian_v1_launcher.py where` tells you what the
icon would do without doing it.

---

## Setup, in order

Every command is run from the project folder with the project's Python: `.venv/bin/python <script> ...`.

### 1. Run the setup wizard (writes a candidate file; changes nothing live)
Easiest: double-click **Start Guardian** (above). Or, in Terminal, in the project folder, run `.venv/bin/python guardian_v1_setup_web.py`. It prints a line like
`Open:  http://127.0.0.1:8766/`. Copy that address into a web browser on the same Mac and the setup page appears. (Only
this Mac can reach the page; no other computer on your network can.) The page walks you through the ASIAIR address, roof
feed, power controller kind and address, and which outlet is the host computer, ASIAIR, mount and accessories. Each
address has a read-only "Check" button. The end result is one new file, `config.guardian-candidate.yaml`. Review it by
eye. The wizard never asks for passwords.

### 2. Save the controller sign-in
Kasa: `.venv/bin/python guardian_v1_credentials.py set kasa`. Digital Loggers: `... set dli`. You type the user name;
macOS asks for the password in its own hidden prompt. Guardian never sees it. `check kasa` says whether it is saved.

### 3. Check your outlet names against the real controller (read-only)
`.venv/bin/python guardian_v1_check_outlets.py --config <your config>`. Every mapped name must match exactly (capital
letters and spaces count). Fix names in the controller's app or in your config until it says all match.

### 4. Put the configuration in place and create the watching-only monitor
A brand-new install: copy the candidate to `config/config.yaml`. Then:
`.venv/bin/python guardian_v1_install_monitor.py --config config/config.yaml` shows the monitor job;
add `--write` to create it. It cannot cut power. Load it with the `launchctl bootstrap` command it prints, then run
`.venv/bin/python guardian_stage_b.py status` (expect: v1.0 running, watching only, disarmed).

### 5. Watch for a few nights
Let the monitor watch your real nights. `.venv/bin/python guardian_v1_nights.py --nights 10` summarises roof closures
and ASIAIR losses. Does it see your ASIAIR and your roof correctly?

### 6. Commission it (you prove each protection works on your rig)
`.venv/bin/python guardian_v1_commissioning_template.py --installation-config config/config.yaml --output <record.json>`
writes a record with eight checks, all NOT_TESTED: ASIAIR monitoring, observatory safety, ASIAIR / mount / accessories
safety power, Guardian survival, simultaneous paths, protection logic. **You** mark a check VERIFIED only after you have
physically seen it work, and fill in who approved and when. Useful tools, all of which follow your outlet mapping:
- `guardian_v1_outlet_test.py list`, then `test --outlet N --expect-alias NAME`: runs Guardian's real power-off on ONE
  spare outlet with nothing plugged in.
- `guardian_v1_rehearsal.py --dry-run`, then the real run with the confirmation word the dry run prints: a simulated roof
  closure (or other trigger) that really cuts your three outlets, with a fresh independent read afterwards. Do this
  only when the equipment is safe to switch off. You power it back on yourself.
- `guardian_v1_commissioning_template.py --check <record.json>` tells you what Guardian will make of the record.
Changing the outlet mapping, controller type or addresses changes the configuration fingerprint: commissioning must
then be redone.

### 7. Build and open the app
Easiest: double-click **Start Guardian**; it builds the app if needed and opens it. Or, in Terminal, in the project folder, run `./build_on_mac.sh`. It needs Apple's command-line developer tools (if they are
missing it says so; install them with `xcode-select --install`). It creates **Guardian 1.0.app** inside the project
folder, for example `~/ObservatorySupervisor/Guardian 1.0.app`.

To open it, either double-click it in Finder, or run:
`open ~/ObservatorySupervisor/"Guardian 1.0.app"`.
The first time, macOS may say it cannot verify the developer. Right-click (or Control-click) the app, choose **Open**,
and confirm. After that it opens normally. For convenience you can drag it to the Dock.

This is the app where you ARM and DISARM. The window shows connection, session, roof, the ASIAIR controller,
hardware-execution and recovery state, and the ARM / DISARM / ACKNOWLEDGE ABORT / ALLOW NEW SESSION buttons (only the
ones that apply are enabled). If it says "Connected" the monitor is running; if it cannot connect, check
`guardian_stage_b.py status` and that the monitor job is loaded. Rebuilding is only needed when you receive a new
version of the app; close the old window first (Command-Q).

### 8. Let Guardian cut power (Stage B: your explicit decision)
Do this in daylight, at the keyboard, never at dusk. `.venv/bin/python guardian_stage_b.py switch` is a dry run; 
`switch --apply` asks you to type `CUT POWER`. It enables hardware execution on the
monitor, and leaves it **disarmed**. `guardian_stage_b.py rollback --apply` undoes it at any time.

### 9. ARM and supervise the first night
Open the app and ARM. You may arm with the roof closed: Guardian waits (`WAITING_FOR_ROOF`) and starts protecting when
the roof opens and imaging is permitted. Stay reachable for the first night. Afterwards, check the log
(`logs/guardian_v1.log`) and `guardian_v1_nights.py`.

---

## After a cut
1. The app shows an aborted session and Guardian is disarmed. Equipment is off.
2. Do not power anything back on until you know why and the roof is safe.
3. Power the equipment on yourself (controller app), then in the Guardian app acknowledge the abort / allow a new
   session if it offers those buttons, and ARM again before imaging.

## If something looks wrong
- DISARM in the app. If you need to go back to the earlier supervisor: `guardian_stage_b.py rollback --apply`.
- `guardian_stage_b.py status` always tells you who is protecting the rig (`PROTECTED_BY`).

---

## Known limits (please read)
- The full new-operator path (steps 1 to 9) has not yet been run start to finish on a clean second machine. The pieces
  are tested individually and against simulated hardware, and Guardian is running live on the author's rig. Expect rough
  edges.
- Digital Loggers support is untested on real hardware.
- The Setup screen inside the app can inspect but not edit the outlet mapping; use the web wizard and create a new
  candidate instead.
- Some early scripts (`guardian_v1_phase_b_*`, `guardian_v1_evidence_audit.py --launchagent`, `guardian_v1_evidence_gaps.py`)
  were written for the author's original set-up and are not part of this path.
- The roof-closing-and-reopening-within-a-session case and an ASIAIR that drops out for a long time are rare and are
  not treated specially; Guardian's response to either is to cut.
- Guardian protects the equipment from a roof it cannot see closing only as well as the roof feed is accurate.
