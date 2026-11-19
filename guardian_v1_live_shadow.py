"""Guardian 1.0 live observation launcher. No hardware control."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from modules.config_loader import load_config
from modules.commissioning import (
    CommissioningStatus,
    CommissioningCheck,
    CommissioningResult,
)
from modules.asiair_state import AsiairStateTracker
from modules.asiair_icmp_adapter import AsiairIcmpAdapter
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)
from modules.alpaca_observatory_adapter import AlpacaObservatorySafetyAdapter
from modules.wave_interface import WaveInterface
from modules.wave_mount_adapter import WaveMountAdapter
from modules.guardian_v1_shadow_runtime import GuardianV1ShadowRuntime
from modules.guardian_v1_shadow_monitor import GuardianV1ShadowMonitor

from guardian_v1 import build_application
from modules.guardian_types import SafetyPowerRole
from modules.safety_power import SafetyPowerEndpoint, SafetyPowerTopology
from modules.kasa_safety_power_adapter import (
    KasaEndpointConfig,
    PythonKasaTransport,
)
from modules.kasa_read_only_adapter import KasaReadOnlyAdapter
from modules.keychain import get_secret
import os


def forbidden_action(*args, **kwargs):
    raise RuntimeError("Hardware action forbidden in live shadow mode")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cycles", type=int, default=None,
        help="Number of read-only observation cycles (default: continuous)",
    )
    parser.add_argument(
        "--simulate-armed",
        action="store_true",
        help="Test-only simulated ARMED evaluation; hardware remains disabled",
    )
    args = parser.parse_args()

    if args.cycles is not None and args.cycles < 1:
        parser.error("--cycles must be at least 1")

    config = load_config()
    app = build_application()

    if app.mode.hardware_execution_enabled:
        raise RuntimeError("Guardian 1.0 must remain monitor-only")

    if config["roof"]["source"] != "alpaca":
        raise RuntimeError("Live shadow requires Alpaca roof source")

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("guardian_v1.shadow")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_dir / "guardian_v1_shadow.log",
        maxBytes=2_000_000,
        backupCount=3,
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
    )
    logger.addHandler(handler)

    asiair = AsiairIcmpAdapter(
        host=config["asiair"]["ip_address"],
        timeout_seconds=config["asiair"]["timeout_seconds"],
    )

    observatory = AlpacaObservatorySafetyAdapter(
        host=config["roof"]["alpaca_host"],
        port=config["roof"]["alpaca_port"],
        device_number=config["roof"]["alpaca_device_number"],
        timeout_seconds=config["roof"]["alpaca_timeout_seconds"],
    )

    wave = WaveInterface(
        host=config["wave"]["host"],
        port=config["wave"]["port"],
        timeout=config["wave"]["timeout_seconds"],
    )

    mount = WaveMountAdapter(
        wave=wave,
        recovery=lambda: False,
        sample_interval_seconds=config["wave"]["motion_sample_interval_seconds"],
    )

    kasa_username = os.environ.get("KASA_USERNAME")
    kasa_password = os.environ.get("KASA_PASSWORD")

    if not (kasa_username and kasa_password):
        kasa_username = get_secret(
            "guardian", "Guardian Kasa Username"
        )
        kasa_password = get_secret(
            "guardian", "Guardian Kasa Password"
        )

    kasa_transport = PythonKasaTransport(
        host=config["kasa"]["power_strip_ip"],
        username=kasa_username,
        password=kasa_password,
    )

    kasa_adapter = KasaReadOnlyAdapter(
        controller_id="hs300",
        endpoints={
            "asiair": KasaEndpointConfig(2, "ASIAIR"),
            "mount": KasaEndpointConfig(3, "Wave 150i"),
        },
        transport=kasa_transport,
    )

    safety_power_topology = SafetyPowerTopology(
        role_endpoints={
            SafetyPowerRole.ASIAIR: SafetyPowerEndpoint(
                "hs300", "asiair"
            ),
            SafetyPowerRole.MOUNT: SafetyPowerEndpoint(
                "hs300", "mount"
            ),
        }
    )

    shadow_fingerprint = "uncommissioned-shadow-observation"

    if args.simulate_armed:
        commissioning = CommissioningStatus(
            results={
                check: CommissioningResult.VERIFIED
                for check in CommissioningCheck
            },
            configuration_fingerprint=shadow_fingerprint,
        )
    else:
        commissioning = CommissioningStatus(results={})

    runtime = GuardianV1ShadowRuntime(
        application=app,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=asiair,
        observatory_adapter=observatory,
        mount_adapter=mount,
        safety_power_topology=safety_power_topology,
        safety_power_adapters={"hs300": kasa_adapter},
        roof_max_age_seconds=10,
        commissioning=commissioning,
        configuration_fingerprint=shadow_fingerprint,
        execute_action=forbidden_action,
        execute_safety_power=forbidden_action,
    )

    monitor = GuardianV1ShadowMonitor(
        runtime=runtime,
        application=app,
        interval_seconds=5,
    )

    print("Guardian 1.0 — LIVE SHADOW")
    print("Hardware execution: DISABLED")
    print(
        "Session: SIMULATED_ARMED (TEST ONLY)"
        if args.simulate_armed
        else "Session: DISARMED"
    )
    print(f"Observation cycles: {args.cycles or 'CONTINUOUS'}")
    print("Log: logs/guardian_v1_shadow.log")

    if args.simulate_armed:
        logger.warning(
            "SIMULATED_ARMED TEST ONLY — commissioning is synthetic; "
            "no hardware commands permitted"
        )

    completed = monitor.run(
        armed=args.simulate_armed,
        cycles=args.cycles,
    )

    print(f"Completed cycles: {completed}")


if __name__ == "__main__":
    main()
