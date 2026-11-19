import pytest

from modules.guardian_config import (
    SafetyConfiguration,
    safety_configuration_fingerprint,
)


def configuration():
    return SafetyConfiguration(
        asiair={"method": "icmp", "host": "asiair"},
        observatory_safety={
            "adapter": "alpaca",
            "device": 17,
        },
        mount={
            "adapter": "wave",
            "endpoint": "mount-control",
        },
        safety_power={
            "roles": {
                "ASIAIR": "controller-1/output-1",
                "MOUNT": "controller-1/output-2",
            },
            "resources": frozenset({"local-lan", "guardian-host"}),
        },
        guardian={
            "required_resources": frozenset(
                {"local-lan", "guardian-host"}
            )
        },
    )


def test_same_configuration_has_same_fingerprint():
    first = configuration()
    second = configuration()

    assert (
        safety_configuration_fingerprint(first)
        == safety_configuration_fingerprint(second)
    )


def test_mapping_order_does_not_change_fingerprint():
    first = configuration()

    second = SafetyConfiguration(
        asiair={"host": "asiair", "method": "icmp"},
        observatory_safety={
            "device": 17,
            "adapter": "alpaca",
        },
        mount={
            "endpoint": "mount-control",
            "adapter": "wave",
        },
        safety_power={
            "resources": frozenset(
                {"guardian-host", "local-lan"}
            ),
            "roles": {
                "MOUNT": "controller-1/output-2",
                "ASIAIR": "controller-1/output-1",
            },
        },
        guardian={
            "required_resources": frozenset(
                {"guardian-host", "local-lan"}
            )
        },
    )

    assert (
        safety_configuration_fingerprint(first)
        == safety_configuration_fingerprint(second)
    )


def test_safety_relevant_change_changes_fingerprint():
    first = configuration()

    second = SafetyConfiguration(
        asiair={"method": "icmp", "host": "asiair"},
        observatory_safety={
            "adapter": "alpaca",
            "device": 17,
        },
        mount={
            "adapter": "wave",
            "endpoint": "mount-control",
        },
        safety_power={
            "roles": {
                "ASIAIR": "controller-1/output-9",
                "MOUNT": "controller-1/output-2",
            },
            "resources": frozenset({"local-lan", "guardian-host"}),
        },
        guardian={
            "required_resources": frozenset(
                {"local-lan", "guardian-host"}
            )
        },
    )

    assert (
        safety_configuration_fingerprint(first)
        != safety_configuration_fingerprint(second)
    )


def test_unsupported_value_is_rejected():
    config = configuration()
    config = SafetyConfiguration(
        asiair={"invalid": object()},
        observatory_safety=config.observatory_safety,
        mount=config.mount,
        safety_power=config.safety_power,
        guardian=config.guardian,
    )

    with pytest.raises(TypeError):
        safety_configuration_fingerprint(config)
