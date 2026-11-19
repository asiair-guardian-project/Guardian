"""A fully simulated Guardian 1.0 rig for rehearsing the abort / acknowledge / release / re-arm flow.

EVERYTHING here is simulated: the roof, the ASIAIR, the UPS and the power strip are in-memory
stand-ins controlled by small text files in a throw-away folder. The real Guardian 1.0 runtime,
gate, supervisor, recovery file and operator socket are used, but on a separate socket and a
separate recovery file, so the live monitor, the live strip and the live recovery state are
never touched. No network connection is made and nothing is sent to the real Kasa strip.

Control the simulated weather by writing one word to a file in the rehearsal folder:
    roof.txt     OPEN | CLOSED | FEED_DOWN (the roof reading fails)
    asiair.txt   ONLINE | OFFLINE
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from modules.commissioning import CommissioningCheck
from modules.guardian_types import RoofState, SafetyPowerState
from modules.guardian_v1_commissioning_record import SCHEMA
from modules.guardian_v1_configuration_identity import semantic_fingerprint
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.observatory_safety import ObservatorySafetyObservation
from modules.runtime_supervisor import RuntimeSupervisor
from modules.ups_adapter import UpsReading

INSTALLATION = {
    "asiair": {"ip_address": "192.0.2.10", "timeout_seconds": 2},      # 192.0.2.x: documentation addresses,
    "kasa": {"power_strip_ip": "192.0.2.20"},                          # not routable, never contacted
    "roof": {"source": "alpaca", "alpaca_host": "alpaca.example.invalid",
             "alpaca_port": 443, "alpaca_device_number": 17,
             "alpaca_timeout_seconds": 5, "stale_after_seconds": None},
    "monitor": {"interval_seconds": 2},
}
OUTLET_NAMES = {2: "ASIAIR", 3: "Wave 150i", 4: "Pegasus"}
ROOF_WORDS = ("OPEN", "CLOSED", "FEED_DOWN")
ASIAIR_WORDS = ("ONLINE", "OFFLINE")


class SimRig:
    """The simulated equipment. State words live in files so a person can change them."""

    def __init__(self, folder, say=print, clock=None, outlet_names=None):
        self.outlet_names = dict(outlet_names or OUTLET_NAMES)   # simulated strip: outlet number -> name
        self.clock = clock or (lambda: datetime.now(timezone.utc))   # tests may drive a synthetic clock
        self.folder = Path(folder)
        self.say = say
        self.roof_file = self.folder / "roof.txt"
        self.asiair_file = self.folder / "asiair.txt"
        self.strip_file = self.folder / "strip.txt"
        self.on = {number: True for number in self.outlet_names}
        self.cuts = []
        self.set_roof("OPEN")
        self.set_asiair("ONLINE")
        self._write_strip()

    # ---- control (also usable from tests)
    def set_roof(self, word):
        if word not in ROOF_WORDS:
            raise ValueError(word)
        self.roof_file.write_text(word + "\n")

    def set_asiair(self, word):
        if word not in ASIAIR_WORDS:
            raise ValueError(word)
        self.asiair_file.write_text(word + "\n")

    def power_everything_back_on(self):
        """What a person does by hand after an abort (the simulated strip's outlets only)."""
        self.on = {number: True for number in self.outlet_names}
        self._write_strip()

    def _write_strip(self):
        lines = [f"outlet {n} ({self.outlet_names[n]}): {'ON' if self.on[n] else 'OFF'}" for n in sorted(self.on)]
        self.strip_file.write_text("\n".join(lines) + "\n")

    def _word(self, path, default):
        try:
            return path.read_text().strip().upper()
        except OSError:
            return default

    # ---- adapters handed to the real runtime
    def roof_adapter(self):
        rig = self

        class Roof:
            def observe(self):
                word = rig._word(rig.roof_file, "FEED_DOWN")
                if word == "OPEN":
                    state = RoofState.OPEN
                elif word == "CLOSED":
                    state = RoofState.CLOSED
                else:
                    raise OSError("simulated roof feed is down")
                return ObservatorySafetyObservation(state=state, observed_at=rig.clock())

        return Roof()

    def asiair_adapter(self):
        rig = self

        class Asiair:
            def is_reachable(self):
                return rig._word(rig.asiair_file, "OFFLINE") == "ONLINE"

        return Asiair()

    def ups_adapter(self):
        class Ups:
            def read(self):
                return UpsReading(on_battery=False, battery_percent=100)

        return Ups()

    def kasa_transport(self):
        rig = self

        class Strip:
            def check_outlet(self, number, alias):
                return rig.outlet_names.get(number) == alias

            def get_outlet_state(self, number, alias):
                return SafetyPowerState.ON if rig.on[number] else SafetyPowerState.OFF

            def power_off_outlet(self, number, alias):
                if rig.outlet_names.get(number) != alias:
                    return False
                rig.on[number] = False
                rig.cuts.append(number)
                rig._write_strip()
                rig.say(f"  [SIMULATED STRIP] outlet {number} ({alias}) switched OFF")
                return True

            def power_off_outlets(self, requests):
                return {number: self.power_off_outlet(number, alias) for number, alias in requests}

            def get_outlet_states(self, requests):
                return {number: (self.get_outlet_state(number, alias)
                                 if rig.outlet_names.get(number) == alias else None)
                        for number, alias in requests}

        return Strip()


def prepare_folder(folder=None, installation=None):
    """Create the throw-away rehearsal folder with a valid, simulated-only configuration."""
    if folder is None:
        folder = tempfile.mkdtemp(dir="/tmp", prefix="gr-")   # short path: socket paths are length-limited
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)   # the operator socket refuses a folder anyone else could write to
    if any(folder.iterdir()):
        raise FileExistsError(f"{folder} is not empty; use a fresh folder")
    (folder / "project").mkdir()
    config = folder / "config.yaml"
    installation = INSTALLATION if installation is None else installation
    config.write_text(yaml.safe_dump(installation))
    GuardianV1RecoveryStore(folder / "recovery.json").write(RuntimeSupervisor().export_recovery_state())
    record = folder / "commissioning.json"
    record.write_text(json.dumps({
        "schema": SCHEMA,
        "configuration_fingerprint": semantic_fingerprint(installation),
        "approved_by": "REHEARSAL (simulated)", "approved_at": "2026-11-02T12:00:00Z",
        "results": {check.name: "VERIFIED" for check in CommissioningCheck},
    }))
    record.chmod(0o600)
    return folder


def build_sim_monitor(folder, rig):
    """Build the real v1.0 armed runtime on the simulated rig. Starts nothing."""
    import guardian_v1_armed
    from modules.guardian_v1_armed_launch import HARDWARE_TOKEN, build_armed_monitor

    folder = Path(folder)
    installation = yaml.safe_load((folder / "config.yaml").read_text())   # the folder's own configuration
    args = guardian_v1_armed.build_parser().parse_args([
        "--recovery-file", str(folder / "recovery.json"),
        "--operator-socket", str(folder / "operator.sock"),
        "--asiair-host", installation["asiair"]["ip_address"],
        "--alpaca-host", installation["roof"]["alpaca_host"],
        "--alpaca-port", str(installation["roof"]["alpaca_port"]),
        "--alpaca-device", str(installation["roof"]["alpaca_device_number"]),
        "--installation-config", str(folder / "config.yaml"),
        "--kasa-host", installation["kasa"]["power_strip_ip"],
        "--commissioning-record", str(folder / "commissioning.json"),
        "--cycle-seconds", str(installation["monitor"]["interval_seconds"]),
        "--enable-hardware-execution", HARDWARE_TOKEN,   # safe here: the only "hardware" is the in-memory strip
    ])
    runner, _commissioning, _identity = build_armed_monitor(
        args, project_root=folder / "project",
        kasa_transport=rig.kasa_transport(), asiair_adapter=rig.asiair_adapter(),
        observatory_adapter=rig.roof_adapter(), ups_adapter=rig.ups_adapter(), send_alert=None)
    return runner
