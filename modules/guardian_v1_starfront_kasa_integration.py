"""Isolated Starfront Kasa integration composition.

Construction is monitor-only. No launchd entrypoint is changed. This
connects the existing observation/evaluation pipeline to the existing
Kasa safety-power routing callback, behind GuardianV1Execution's mode gate.
"""
from modules.alpaca_observatory_adapter import AlpacaObservatorySafetyAdapter
from modules.asiair_icmp_adapter import AsiairIcmpAdapter
from modules.asiair_state import DEFAULT_LOST_AFTER_MISSES
from modules.safety_power_probe_schedule import (
    DEFAULT_CHECK_INTERVAL_SECONDS,
    SafetyPowerProbeSchedule,
)
from modules.asiair_state import AsiairStateTracker
from modules.commissioning import CommissioningStatus
from modules.guardian_v1_shadow_runtime import GuardianV1ShadowRuntime
from modules.guardian_v1_starfront_kasa import compose_starfront_kasa
from modules.guardian_v1_mapped_kasa import compose_mapped_kasa
from modules.ups_adapter import DEFAULT_UNREADABLE_GRACE_SECONDS
from modules.observatory_observation_coordinator import ObservatoryObservationCoordinator


def _no_mount_commands(*args, **kwargs):
    raise RuntimeError("Direct mount commands are not configured")


def compose_starfront_kasa_integration(
    *, application, asiair_host, alpaca_host, alpaca_port,
    alpaca_device_number, kasa_host, commissioning=None,
    configuration_fingerprint="uncommissioned", roof_max_age_seconds=30,
    kasa_transport=None, asiair_adapter=None, observatory_adapter=None,
    ups_adapter=None, ups_low_battery_percent=35,
    ups_unreadable_grace_seconds=DEFAULT_UNREADABLE_GRACE_SECONDS,
    asiair_lost_after_misses=DEFAULT_LOST_AFTER_MISSES,
    strip_check_seconds=DEFAULT_CHECK_INTERVAL_SECONDS,
    strip_check_clock=None, power_mapping=None,
):
    """Wire existing observation and Kasa modules; do not enable execution.

    For simulated tests, supply fake Kasa and observation adapters.
    Actual hardware execution requires a separate explicit commissioning
    and runtime path, which this function does not install.
    """
    if application.mode.hardware_execution_enabled:
        raise RuntimeError("Integration composition must start monitor-only")
    if application.recovery_store is None:
        raise ValueError("Durable recovery store required")
    if roof_max_age_seconds <= 0:
        raise ValueError("Roof freshness must be positive")

    if power_mapping is None:
        wiring = compose_starfront_kasa(host=kasa_host, transport=kasa_transport)   # the fixed Starfront layout
    else:
        wiring = compose_mapped_kasa(host=kasa_host, mapping=power_mapping, transport=kasa_transport)
    runtime = GuardianV1ShadowRuntime(
        application=application,
        asiair_tracker=AsiairStateTracker(asiair_lost_after_misses),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=asiair_adapter or AsiairIcmpAdapter(asiair_host),
        observatory_adapter=observatory_adapter or AlpacaObservatorySafetyAdapter(
            host=alpaca_host, port=alpaca_port,
            device_number=alpaca_device_number,
        ),
        safety_power_topology=wiring.topology,
        safety_power_adapters=wiring.adapters,
        roof_max_age_seconds=roof_max_age_seconds,
        commissioning=commissioning if commissioning is not None else CommissioningStatus(results={}),
        configuration_fingerprint=configuration_fingerprint,
        execute_action=_no_mount_commands,
        execute_safety_power=wiring.execute_safety_power,
        ups_adapter=ups_adapter,
        ups_low_battery_percent=ups_low_battery_percent,
        ups_unreadable_grace_seconds=ups_unreadable_grace_seconds,
        safety_power_schedule=SafetyPowerProbeSchedule(
            interval_seconds=strip_check_seconds,
            **({"clock": strip_check_clock} if strip_check_clock else {}),
        ),
    )
    return runtime
