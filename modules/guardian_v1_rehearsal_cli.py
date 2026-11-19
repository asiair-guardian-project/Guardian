"""Command-line wrapper for the commissioning rehearsal (see guardian_v1_rehearsal)."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

from modules.guardian_v1_rehearsal import (
    CONFIRM_TOKEN,
    SCENARIOS,
    RehearsalRefused,
    run_rehearsal,
    target_requests,
    write_evidence,
)

DEFAULT_EVIDENCE_DIR = Path.home() / "Library/Application Support/GuardianV1/rehearsals"
DEFAULT_SOCKET = Path.home() / "Library/Application Support/GuardianV1/operator.sock"


def _find(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _find(value, key)
            if found is not None:
                return found
    return None


def live_monitor_is_armed(socket_path) -> str | None:
    """Return a reason to refuse, or None. Unclear answers refuse (fail safe)."""

    path = Path(socket_path)
    if not path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(str(path))
            s.sendall(b'{"command": "STATUS"}\n')
            raw = b""
            while b"\n" not in raw and len(raw) < 65536:
                part = s.recv(4096)
                if not part:
                    break
                raw += part
        data = json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))
    except (ConnectionRefusedError, FileNotFoundError):
        return None  # stale socket file, nobody listening
    except (OSError, ValueError, UnicodeError):
        return "a monitor is listening but its status could not be read"
    if _find(data, "armed") is True or _find(data, "hardware_execution_enabled") is True:
        return "a live Guardian monitor reports ARMED or hardware execution enabled"
    return None


def build_parser():
    import argparse

    p = argparse.ArgumentParser(
        description="Guardian commissioning rehearsal: simulated trigger, REAL power cut.",
        allow_abbrev=False)
    p.add_argument("--installation-config", required=True)
    p.add_argument("--kasa-host", required=True)
    p.add_argument("--scenario", choices=SCENARIOS, default="roof-closed")
    p.add_argument("--confirm", default=None, metavar="CUT_OUTLETS_<numbers>",
                   help="the token printed by --dry-run (Starfront wiring: " + CONFIRM_TOKEN + ")")
    p.add_argument("--allow-already-off", action="store_true")
    p.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    p.add_argument("--operator-socket", default=str(DEFAULT_SOCKET))
    p.add_argument("--dry-run", action="store_true",
                   help="Read the outlets and run every safety check; switch nothing.")
    return p


def main(argv=None, *, project_root=None, transport=None, input_fn=input,
         out=print, v06_check=None) -> int:
    args = build_parser().parse_args(argv)
    project_root = project_root or Path(__file__).resolve().parent.parent

    try:
        from modules.guardian_v1_armed_launch import v06_running
        from modules.guardian_v1_configuration_identity import semantic_fingerprint
        from modules.guardian_v1_setup_config import read_installation

        installation = read_installation(args.installation_config)
        from modules.guardian_v1_layout import layout_from_installation
        layout = layout_from_installation(installation)
        fingerprint = semantic_fingerprint(installation)

        if (installation.get("kasa") or {}).get("power_strip_ip") != args.kasa_host:
            raise RehearsalRefused("--kasa-host does not match kasa.power_strip_ip in the YAML")
        if (v06_check or v06_running)(project_root):
            raise RehearsalRefused("Guardian v0.6 is running; stop it first")
        reason = live_monitor_is_armed(args.operator_socket)
        if reason:
            raise RehearsalRefused(reason)

        if transport is None and layout.controller_type == "digital_loggers_rest":
            from modules.guardian_v1_dli_transport import DigitalLoggersTransport, dli_credentials

            user, password = dli_credentials()
            options = layout.options or {}
            transport = DigitalLoggersTransport(host=args.kasa_host, username=user, password=password,
                                                port=options.get("port"), scheme=options.get("scheme", "http"))
        elif transport is None:
            from modules.kasa_controller import KasaController
            from modules.kasa_safety_power_adapter import PythonKasaTransport

            user, password = KasaController(args.kasa_host)._credentials()
            transport = PythonKasaTransport(host=args.kasa_host, username=user, password=password)

        from modules.guardian_v1_rehearsal import preflight

        before, protected = preflight(transport, allow_already_off=args.allow_already_off, layout=layout)
        out("Outlets now (read from the real strip):")
        for number, alias in target_requests(layout):
            out(f"  {number} {alias}: {before[number].name}")
        for number, state in protected.items():
            out(f"  {number} (protected, never switched): {state.name}")

        if args.dry_run:
            out("DRY RUN: all checks passed. Nothing was switched.")
            out(f"To run for real, add:  --confirm {layout.confirm_token}")
            return 0

        token = layout.confirm_token
        numbers = sorted(t.number for t in layout.targets)
        if args.confirm != token:
            raise RehearsalRefused(f"add  --confirm {token}  to run for real")
        out(f"\nScenario '{args.scenario}' will CUT POWER to outlets {numbers[0]}, {numbers[1]} and {numbers[2]} now.")
        if input_fn("Type CUT to proceed: ").strip() != "CUT":
            raise RehearsalRefused("not confirmed; nothing switched")

        result = run_rehearsal(
            scenario=args.scenario, transport=transport,
            configuration_fingerprint=fingerprint,
            allow_already_off=args.allow_already_off, layout=layout)
        path = write_evidence(result, args.evidence_dir,
                              configuration_fingerprint=fingerprint, kasa_host=args.kasa_host)
    except RehearsalRefused as refusal:
        out(f"REFUSED: {refusal}\nNothing was switched by this refusal.")
        return 2
    except Exception as error:
        out(f"ERROR before completion: {type(error).__name__}: {error}")
        return 3

    out(f"\nResult: {'PASS' if result.passed else 'FAIL'}")
    out(f"  trigger expected {result.expected_trigger}, observed {result.observed_triggers}")
    out(f"  outlets after (fresh read): {result.outlets_after}")
    out(f"  protected outlet after:     {result.protected_after}")
    out(f"  trigger to verified-off:    {result.seconds_trigger_to_resolved} s")
    out(f"  evidence file: {path}")
    out("Power the equipment back on yourself. This is evidence only; it does not approve commissioning.")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
