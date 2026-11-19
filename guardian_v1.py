"""Guardian 1.0 shadow-mode entry point."""

import argparse
import os
import signal
import stat
from pathlib import Path

from modules.guardian_types import Capability
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore


CONFIGURED_CAPABILITIES = {
    Capability.ASIAIR_MONITORING,
    Capability.OBSERVATORY_SAFETY_MONITORING,
    Capability.SAFETY_POWER_CONTROL,
    Capability.SAFETY_POWER_STATE_VERIFICATION,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the Guardian 1.0 shadow-mode command-line parser."""

    parser = argparse.ArgumentParser(
        description="Guardian 1.0 Observatory Supervisor — shadow mode"
    )

    parser.set_defaults(shadow=True)
    parser.add_argument(
        "--recovery-file", default=None,
        help="Explicit Guardian v1 recovery JSON path (never creates or resets it)",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print read-only operator recovery status",
    )

    parser.add_argument(
        "--operator-service", action="store_true",
        help="Run the serialized local operator command service (monitor-only; no hardware)",
    )
    parser.add_argument(
        "--operator-socket", default=None,
        help="Explicit local Unix socket path in a private 0700 directory",
    )
    parser.add_argument("--continuous-monitor", action="store_true",
                        help="Run unified read-only monitoring and operator IPC")
    parser.add_argument("--check-installation-config", metavar="YAML_PATH",
                        help="Read-only comparison of YAML to explicit monitor launch settings; exits without starting")
    parser.add_argument("--installation-config", default=None,
                        help="Optional read-only installation YAML for operator setup inspection")
    parser.add_argument("--asiair-host")
    parser.add_argument("--alpaca-host")
    parser.add_argument("--alpaca-port", type=int)
    parser.add_argument("--alpaca-device", type=int, default=17)
    parser.add_argument("--cycle-seconds", type=float, default=5.0)
    return parser


def build_application(*, recovery_file=None) -> GuardianV1Application:
    """Construct Guardian 1.0 in its safe default monitor-only mode."""

    return GuardianV1Application(
        configured_capabilities=CONFIGURED_CAPABILITIES,
        recovery_store=(
            GuardianV1RecoveryStore(recovery_file)
            if recovery_file is not None else None
        ),
    )


def main() -> None:
    args = build_parser().parse_args()

    if args.check_installation_config is not None:
        from modules.guardian_v1_setup_config import read_installation, SetupValidationError
        from modules.guardian_v1_setup_binding import MonitorBinding, compare_monitor_binding
        if not (args.asiair_host and args.alpaca_host and args.alpaca_port):
            raise SystemExit("Comparison requires --asiair-host, --alpaca-host and --alpaca-port")
        try:
            configuration = read_installation(args.check_installation_config)
            comparison = compare_monitor_binding(configuration, MonitorBinding(
                asiair_host=args.asiair_host, alpaca_host=args.alpaca_host,
                alpaca_port=args.alpaca_port, alpaca_device=args.alpaca_device,
                cycle_seconds=args.cycle_seconds))
        except (OSError, SetupValidationError) as exc:
            raise SystemExit(f"Configuration comparison unavailable: {type(exc).__name__}") from exc
        if not comparison['matches_active_monitor']:
            print("CONFIGURATION MISMATCH — no changes applied")
            for difference in comparison['differences']:
                print(difference)
            raise SystemExit(2)
        print("CONFIGURATION MATCH — read-only; commissioning NOT AUTHORIZED")
        return

    app = build_application(recovery_file=args.recovery_file)

    if args.continuous_monitor:
        if not (args.recovery_file and args.operator_socket and args.asiair_host
                and args.alpaca_host and args.alpaca_port):
            raise SystemExit("Continuous monitor requires recovery-file, operator-socket, "
                             "asiair-host, alpaca-host and alpaca-port")
        if args.cycle_seconds <= 0:
            raise SystemExit("--cycle-seconds must be positive")
        from modules.guardian_v1_starfront_composition import compose_starfront_read_only
        from modules.guardian_v1_unified_runtime import GuardianV1UnifiedRuntime
        # Bind the running monitor to the validated installation identity.
        # This is a startup gate only; it cannot authorize commissioning or hardware.
        if not args.installation_config:
            raise SystemExit("Continuous monitor requires --installation-config")
        from modules.guardian_v1_setup_config import read_installation, SetupValidationError
        from modules.guardian_v1_setup_binding import MonitorBinding, compare_monitor_binding
        from modules.guardian_v1_configuration_identity import semantic_fingerprint
        from modules.guardian_v1_activation_startup_gate import assert_no_pending_activation
        assert_no_pending_activation(args.installation_config)
        from modules.guardian_v1_setup_inspection import make_setup_provider
        binding = MonitorBinding(
            asiair_host=args.asiair_host, alpaca_host=args.alpaca_host,
            alpaca_port=args.alpaca_port, alpaca_device=args.alpaca_device,
            cycle_seconds=args.cycle_seconds)
        try:
            installation = read_installation(args.installation_config)
            comparison = compare_monitor_binding(installation, binding)
            if not comparison['matches_active_monitor']:
                raise SystemExit("Installation configuration differs from monitor launch settings")
            installation_identity = semantic_fingerprint(installation)
        except (OSError, ValueError, SetupValidationError) as exc:
            raise SystemExit(f"Installation identity unavailable: {type(exc).__name__}") from exc
        observation = compose_starfront_read_only(
            application=app, asiair_host=args.asiair_host,
            alpaca_host=args.alpaca_host, alpaca_port=args.alpaca_port,
            alpaca_device_number=args.alpaca_device,
            configuration_fingerprint=installation_identity)
        setup_provider = make_setup_provider(args.installation_config, binding)
        runner = GuardianV1UnifiedRuntime(
            application=app, observation_runtime=observation,
            socket_path=args.operator_socket, interval_seconds=args.cycle_seconds,
            setup_provider=setup_provider)
        print("Guardian v1 unified monitoring: HARDWARE DISABLED; SESSION DISARMED", flush=True)

        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def handle_sigterm(signum, frame):
            runner.stop()

        signal.signal(signal.SIGTERM, handle_sigterm)
        from modules.guardian_v1_runtime_lock import monitor_lifetime_lock
        # The monitor owns the shared lock through socket shutdown/cleanup.
        runtime_lock_path = Path(args.operator_socket).parent / "runtime.lock"
        try:
            with monitor_lifetime_lock(runtime_lock_path):
                try:
                    runner.run()
                except KeyboardInterrupt:
                    runner.stop()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
        return

    if args.operator_service:
        if not args.recovery_file or not args.operator_socket:
            raise SystemExit("--operator-service requires --recovery-file and --operator-socket")
        from modules.guardian_v1_operator_socket import GuardianOperatorSocket
        service = GuardianOperatorSocket(app, args.operator_socket)
        service.start()
        print("Guardian v1 operator service: MONITOR-ONLY / NO HARDWARE", flush=True)
        print(f"Recovery file: {Path(args.recovery_file).resolve()}", flush=True)
        print(f"Socket: {args.operator_socket}", flush=True)
        try:
            while True:
                service.serve_once()
        except KeyboardInterrupt:
            pass
        finally:
            service.close()
        return

    if args.status:
        print("Guardian 1.0 — Operator recovery status (read-only)")
        if args.recovery_file is None:
            print("Recovery store: NOT CONFIGURED")
            print("ARM status: NOT ASSESSED — no durable recovery store selected")
            return
        print(f"Recovery file: {args.recovery_file}")
        print(f"Session: {app.supervisor.session_state.name}")
        print(f"Recovery required / ARM blocked: {app.supervisor.recovery_blocked or app.supervisor.incident is not None}")
        print(f"Active incident: {'YES' if app.supervisor.incident is not None else 'NO'}")
        print(f"Abort acknowledged: {app.supervisor.abort_acknowledged}")
        print(f"Incident history count: {len(app.supervisor.incident_history)}")
        if app.supervisor.recovery_block_reason:
            print(f"Reason: {app.supervisor.recovery_block_reason}")
        print("Hardware execution: DISABLED")
        return

    print("Guardian 1.0")
    print("Mode: SHADOW / MONITOR-ONLY")
    print(
        "Hardware execution: "
        f"{'ENABLED' if app.mode.hardware_execution_enabled else 'DISABLED'}"
    )


if __name__ == "__main__":
    main()
