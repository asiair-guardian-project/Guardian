# Guardian

**Beta. Community-tested only. Read the safety notice first.**

Guardian is a safety supervisor for remote astroimaging rigs that **cannot protect themselves**. With an
ASIAIR controller you cannot pause imaging or shut down unattended, so when the roof closes (or the ASIAIR drops
off the network, or a UPS runs low) Guardian does the one thing that always works: it **cuts power to the
equipment** through a smart power strip and reads every outlet back to confirm it is off.

It was built for one real rig (an ASIAIR and a Kasa HS300 strip at Starfront Observatories, Texas) and has
protected it through real roof closures. It is shared here as a scaffold for others to try and adapt.

## Safety notice

- Guardian is a safety **aid**, not a guarantee. Commission it yourself, test every outlet, and keep supervising.
- It only cuts power. It never turns anything back on, parks the mount, or closes the roof.
- It does not help if the computer running it is off, or if your internet and strip both fail.
- Kasa HS300 support is tested on real hardware. **Digital Loggers support is untested on real hardware.**
- Provided "as is" under the MIT licence, with no warranty. You are responsible for your equipment.

## Start here

1. [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md): what it will and won't do, and the setup steps in order.
2. [`docs/GUARDIAN_1.0_ARCHITECTURE.md`](docs/GUARDIAN_1.0_ARCHITECTURE.md): how it decides to cut power.
3. [`config/config.example.yaml`](config/config.example.yaml): shape of the configuration (the setup wizard
   writes your real one).

**Coming back after a while?** Run `.venv/bin/python guardian_v1_launcher.py install` once to put a
**Start Guardian** icon on your Desktop; double-click it to continue setup or open the app.

## Requirements

- macOS (the app, launchd jobs and Keychain use are Mac-only today; porting is welcome).
- Python 3 and `pip install -r requirements.txt` in a virtual environment.
- A roof status source that speaks ASCOM Alpaca, a supported power strip, and an always-on computer.

## Running the tests

```
python -m pytest -q
```

A few old tests from earlier development may fail or not collect; please report anything unexpected.

## Status and limits

- The full "new operator" path has not yet been run end to end on a clean second machine. Reports welcome.
- Some early `guardian_v1_phase_b_*` scripts and shadow-mode audit tools reflect the original rig's setup.
- Windows and Linux are not supported.

## Contributing

Issues and pull requests welcome, especially: clean-machine setup reports, other power controllers, other roof
sources, and porting.
