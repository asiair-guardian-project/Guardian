import pytest
from modules.guardian_v1_starfront_kasa_integration import compose_starfront_kasa_integration


def test_refuses_hardware_enabled_application():
    class Mode:
        hardware_execution_enabled = True
    class App:
        mode = Mode()
        recovery_store = object()
    with pytest.raises(RuntimeError, match="monitor-only"):
        compose_starfront_kasa_integration(
            application=App(), asiair_host="example.invalid",
            alpaca_host="example.invalid", alpaca_port=443,
            alpaca_device_number=17, kasa_host="example.invalid",
            kasa_transport=object(),
        )


def test_requires_durable_recovery():
    class Mode:
        hardware_execution_enabled = False
    class App:
        mode = Mode()
        recovery_store = None
    with pytest.raises(ValueError, match="Durable"):
        compose_starfront_kasa_integration(
            application=App(), asiair_host="example.invalid",
            alpaca_host="example.invalid", alpaca_port=443,
            alpaca_device_number=17, kasa_host="example.invalid",
            kasa_transport=object(),
        )
