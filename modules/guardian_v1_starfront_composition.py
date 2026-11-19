"""Monitor-only Starfront composition; never constructs mount or power adapters."""
from modules.alpaca_observatory_adapter import AlpacaObservatorySafetyAdapter
from modules.asiair_icmp_adapter import AsiairIcmpAdapter
from modules.asiair_state import DEFAULT_LOST_AFTER_MISSES
from modules.asiair_state import AsiairStateTracker
from modules.observatory_observation_coordinator import ObservatoryObservationCoordinator
from modules.guardian_v1_shadow_runtime import GuardianV1ShadowRuntime
from modules.commissioning import CommissioningStatus
from modules.ups_adapter import DEFAULT_UNREADABLE_GRACE_SECONDS


def _forbid_hardware(*args, **kwargs):
    raise RuntimeError('Hardware execution forbidden in monitor-only composition')


def compose_starfront_read_only(*, application, asiair_host, alpaca_host,
                                alpaca_port, alpaca_device_number,
                                commissioning=None, configuration_fingerprint='monitor-only',
                                roof_max_age_seconds=30,
                                ups_adapter=None, ups_low_battery_percent=35,
                                ups_unreadable_grace_seconds=DEFAULT_UNREADABLE_GRACE_SECONDS,
                                asiair_lost_after_misses=DEFAULT_LOST_AFTER_MISSES):
    if application.mode.hardware_execution_enabled:
        raise RuntimeError('Hardware must remain disabled')
    if application.recovery_store is None:
        raise ValueError('Durable recovery store required')
    if roof_max_age_seconds <= 0:
        raise ValueError('Roof freshness must be positive')
    return GuardianV1ShadowRuntime(
        application=application,
        asiair_tracker=AsiairStateTracker(asiair_lost_after_misses),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=AsiairIcmpAdapter(asiair_host),
        observatory_adapter=AlpacaObservatorySafetyAdapter(
            host=alpaca_host, port=alpaca_port, device_number=alpaca_device_number),
        safety_power_topology=None, safety_power_adapters=None,
        roof_max_age_seconds=roof_max_age_seconds,
        commissioning=(
            commissioning if commissioning is not None
            else CommissioningStatus(results={})
        ),
        configuration_fingerprint=configuration_fingerprint,
        execute_action=_forbid_hardware, execute_safety_power=_forbid_hardware,
        ups_adapter=ups_adapter, ups_low_battery_percent=ups_low_battery_percent,
        ups_unreadable_grace_seconds=ups_unreadable_grace_seconds)
