"""Launch Guardian 1.0 as an armed-capable monitor.

Reached only through `guardian_v1_armed.py`. The watch-only entry point
(`guardian_v1.py`) is not touched and cannot arm.

Safety rules enforced here, before anything runs:
  * hardware execution stays OFF unless the launch line carries the exact
    token  --enable-hardware-execution YES_CUT_POWER  (ARM is still a separate,
    deliberate operator action, and still needs signed-off commissioning);
  * hardware cannot be enabled while Guardian v0.6 is running;
  * the strip address must match the installation YAML;
  * the installation must match the monitor's launch settings and have no
    pending activation, exactly as the watch-only monitor requires;
  * a missing or invalid commissioning record means ARM is refused, not that
    the monitor fails to start (it stays a watch-only monitor).
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

from modules.guardian_v1_event_journal import EventJournal

HARDWARE_TOKEN = "YES_CUT_POWER"


def v06_running(project_root) -> bool:
    """True if Guardian v0.6's status file shows a live process."""

    status_path = Path(project_root) / "guardian_status.json"

    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
        reported = data.get("running") is True
    except (OSError, ValueError, TypeError, AttributeError):
        return False

    if not reported or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # the process exists but belongs to someone else

    return True


def _require(args):
    needed = {
        "--recovery-file": args.recovery_file,
        "--operator-socket": args.operator_socket,
        "--asiair-host": args.asiair_host,
        "--alpaca-host": args.alpaca_host,
        "--alpaca-port": args.alpaca_port,
        "--installation-config": args.installation_config,
        "--kasa-host": args.kasa_host,
    }
    missing = [name for name, value in needed.items() if not value]

    if missing:
        raise SystemExit(
            "Armed monitor requires " + ", ".join(missing)
        )

    if args.cycle_seconds <= 0:
        raise SystemExit("--cycle-seconds must be positive")

    if args.enable_hardware_execution not in (None, HARDWARE_TOKEN):
        raise SystemExit(
            "--enable-hardware-execution needs the exact confirmation token "
            f"{HARDWARE_TOKEN}"
        )


def build_armed_monitor(
    args,
    *,
    project_root,
    kasa_transport=None,
    asiair_adapter=None,
    observatory_adapter=None,
    ups_adapter=None,
    send_alert=None,
):
    """Build (runner, commissioning_load, installation_identity). Starts nothing."""

    _require(args)

    from modules.abort_alerter import AbortAlerter, AlertLevel
    from modules.guardian_v1_activation_startup_gate import (
        assert_no_pending_activation,
    )
    from modules.guardian_v1_application import GuardianV1Application
    from modules.guardian_v1_armed_gate import GuardianV1ArmedGate
    from modules.guardian_v1_armed_runtime import GuardianV1ArmedRuntime
    from modules.guardian_v1_commissioning_record import (
        load_commissioning_record,
    )
    from modules.guardian_v1_configuration_identity import semantic_fingerprint
    from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
    from modules.guardian_v1_setup_binding import (
        MonitorBinding,
        compare_monitor_binding,
    )
    from modules.guardian_v1_setup_config import (
        SetupValidationError,
        read_installation,
    )
    from modules.guardian_v1_power_mapping import power_mapping_from_installation
    from modules.guardian_v1_setup_inspection import make_setup_provider
    from modules.guardian_v1_starfront_kasa_integration import (
        compose_starfront_kasa_integration,
    )
    from modules.ups_adapter import PmsetUpsAdapter

    hardware_requested = args.enable_hardware_execution == HARDWARE_TOKEN
    alert_level = AlertLevel.parse(args.alert_level)

    if hardware_requested and v06_running(project_root):
        raise SystemExit(
            "Guardian v0.6 is running; refusing to enable hardware execution "
            "while it is. Stop v0.6 first."
        )

    assert_no_pending_activation(args.installation_config)

    binding = MonitorBinding(
        asiair_host=args.asiair_host, alpaca_host=args.alpaca_host,
        alpaca_port=args.alpaca_port, alpaca_device=args.alpaca_device,
        cycle_seconds=args.cycle_seconds)

    try:
        installation = read_installation(args.installation_config)
        comparison = compare_monitor_binding(installation, binding)
        if not comparison["matches_active_monitor"]:
            raise SystemExit(
                "Installation configuration differs from monitor launch settings"
            )
        identity = semantic_fingerprint(installation)
        # No `power` section means the fixed Starfront layout. A present but invalid one stops the monitor starting.
        power_mapping = power_mapping_from_installation(installation)
    except (OSError, ValueError, SetupValidationError) as exc:
        raise SystemExit(
            f"Installation identity unavailable: {type(exc).__name__}"
        ) from exc

    configured_strip = (installation.get("kasa") or {}).get("power_strip_ip")

    if configured_strip != args.kasa_host:
        raise SystemExit(
            "--kasa-host does not match kasa.power_strip_ip in the installation YAML"
        )

    commissioning_load = load_commissioning_record(
        args.commissioning_record, identity
    )

    application = GuardianV1Application(
        configured_capabilities=_configured_capabilities(),
        recovery_store=GuardianV1RecoveryStore(args.recovery_file),
        allow_restart_abort=True,
    )

    observation = compose_starfront_kasa_integration(
        application=application,
        asiair_host=args.asiair_host,
        alpaca_host=args.alpaca_host,
        alpaca_port=args.alpaca_port,
        alpaca_device_number=args.alpaca_device,
        kasa_host=args.kasa_host,
        commissioning=commissioning_load.status,
        configuration_fingerprint=identity,
        kasa_transport=kasa_transport,
        asiair_adapter=asiair_adapter,
        observatory_adapter=observatory_adapter,
        ups_adapter=ups_adapter if ups_adapter is not None else PmsetUpsAdapter(),
        ups_low_battery_percent=args.ups_low_battery_percent,
        ups_unreadable_grace_seconds=args.ups_unreadable_grace_seconds,
        asiair_lost_after_misses=args.asiair_lost_after_misses,
        strip_check_seconds=args.strip_check_seconds,
        power_mapping=power_mapping,
    )

    gate = GuardianV1ArmedGate(
        application=application, observation_runtime=observation,
        arm_blockers=[
            lambda: (
                "Guardian v0.6 is running; stop it before arming v1.0"
                if v06_running(project_root) else None
            )
        ],
    )

    if send_alert is None and alert_level is not AlertLevel.OFF:
        from modules.notification import NotificationEngine

        send_alert = NotificationEngine(
            enabled=True, minimum_level="INFO", pushover_enabled=True
        )._send

    runner = GuardianV1ArmedRuntime(
        application=application,
        gate=gate,
        observation_runtime=observation,
        socket_path=args.operator_socket,
        interval_seconds=args.cycle_seconds,
        enable_hardware_execution=hardware_requested,
        setup_provider=make_setup_provider(args.installation_config, binding),
        alerter=AbortAlerter(alert_level, send_alert),
        journal=EventJournal(Path(project_root) / "logs"),
    )

    return runner, commissioning_load, identity


def _configured_capabilities():
    from modules.guardian_types import Capability

    return {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.SAFETY_POWER_STATE_VERIFICATION,
    }


def run_armed_monitor(args, *, project_root=None, **injected) -> None:
    """Build and run the armed-capable monitor until stopped."""

    from modules.guardian_v1_runtime_lock import monitor_lifetime_lock

    project_root = project_root or Path(__file__).resolve().parent.parent
    runner, commissioning_load, _identity = build_armed_monitor(
        args, project_root=project_root, **injected
    )

    hardware = "ENABLED" if runner.enable_hardware_execution else "DISABLED"
    print(
        f"Guardian v1 ARMED-CAPABLE monitor: HARDWARE {hardware}; "
        f"commissioning: {commissioning_load.reason}; SESSION DISARMED",
        flush=True,
    )

    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def handle_sigterm(signum, frame):
        runner.stop()

    signal.signal(signal.SIGTERM, handle_sigterm)
    lock_path = Path(args.operator_socket).parent / "runtime.lock"

    try:
        with monitor_lifetime_lock(lock_path):
            try:
                runner.run()
            except KeyboardInterrupt:
                runner.stop()
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
