from datetime import timezone

import pytest

from modules.alpaca_observatory_adapter import (
    AlpacaObservatorySafetyAdapter,
)
from modules.guardian_types import RoofState


def adapter():
    return AlpacaObservatorySafetyAdapter(
        host="example.test",
        port=443,
        device_number=17,
    )


def test_safe_maps_to_open(monkeypatch):
    monkeypatch.setattr(
        "modules.alpaca_observatory_adapter.read_alpaca_safety_status",
        lambda *args, **kwargs: {
            "is_safe": True,
            "status": "OPEN",
        },
    )

    result = adapter().observe()

    assert result.state is RoofState.OPEN
    assert result.observed_at.tzinfo is timezone.utc


def test_unsafe_maps_to_closed(monkeypatch):
    monkeypatch.setattr(
        "modules.alpaca_observatory_adapter.read_alpaca_safety_status",
        lambda *args, **kwargs: {
            "is_safe": False,
            "status": "CLOSED",
        },
    )

    result = adapter().observe()

    assert result.state is RoofState.CLOSED


def test_source_error_propagates(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Alpaca unavailable")

    monkeypatch.setattr(
        "modules.alpaca_observatory_adapter.read_alpaca_safety_status",
        fail,
    )

    with pytest.raises(RuntimeError):
        adapter().observe()


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        AlpacaObservatorySafetyAdapter(
            host="",
            port=443,
            device_number=17,
        )

    with pytest.raises(ValueError):
        AlpacaObservatorySafetyAdapter(
            host="example.test",
            port=0,
            device_number=17,
        )

    with pytest.raises(ValueError):
        AlpacaObservatorySafetyAdapter(
            host="example.test",
            port=443,
            device_number=-1,
        )

    with pytest.raises(ValueError):
        AlpacaObservatorySafetyAdapter(
            host="example.test",
            port=443,
            device_number=17,
            timeout_seconds=0,
        )
