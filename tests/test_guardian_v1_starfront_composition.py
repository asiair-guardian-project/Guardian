import pytest
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_recovery_store import GuardianV1RecoveryStore
from modules.guardian_v1_starfront_composition import compose_starfront_read_only


def opts(app):
    return dict(application=app, asiair_host='192.0.2.1',
                alpaca_host='192.0.2.2', alpaca_port=11111, alpaca_device_number=17)


def test_read_only_wiring(tmp_path):
    app = GuardianV1Application(configured_capabilities=set(),
        recovery_store=GuardianV1RecoveryStore(tmp_path / 'missing.json'))
    runtime = compose_starfront_read_only(**opts(app))
    assert runtime._safety_power_adapters is None
    assert runtime._safety_power_topology is None
    assert runtime._asiair_adapter._host == '192.0.2.1'
    assert runtime._observatory_adapter._device_number == 17
    with pytest.raises(RuntimeError, match='forbidden'):
        runtime._execute_action(None)
    with pytest.raises(RuntimeError, match='forbidden'):
        runtime._execute_safety_power(None)


def test_requires_recovery_store():
    app = GuardianV1Application(configured_capabilities=set())
    with pytest.raises(ValueError, match='Durable'):
        compose_starfront_read_only(**opts(app))


def test_rejects_bad_roof_freshness(tmp_path):
    app = GuardianV1Application(configured_capabilities=set(),
        recovery_store=GuardianV1RecoveryStore(tmp_path / 'missing.json'))
    with pytest.raises(ValueError, match='freshness'):
        compose_starfront_read_only(**opts(app), roof_max_age_seconds=0)
