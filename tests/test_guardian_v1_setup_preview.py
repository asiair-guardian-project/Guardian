import yaml
from modules.guardian_v1_setup_binding import MonitorBinding
from modules.guardian_v1_setup_inspection import make_setup_provider


def test_preview_is_memory_only_and_redacted(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"asiair": {"ip_address": "192.0.2.1", "timeout_seconds": 5},
        "roof": {"source": "alpaca", "alpaca_host": "example.org", "alpaca_port": 443,
                 "alpaca_device_number": 17, "stale_after_seconds": 30},
        "monitor": {"interval_seconds": 5}, "kasa": {"power_strip_ip": "192.0.2.3"}}))
    before = path.read_bytes()
    provider = make_setup_provider(path, MonitorBinding("192.0.2.1", "example.org", 443, 17, 5))
    result = provider.preview({"asiair": {"ip_address": "192.0.2.44"}})
    assert result["ok"] and result["valid"] and not result["applied"]
    assert result["changed_fields"] == ["asiair.ip_address"]
    assert not result["matches_active_monitor"]
    assert "192.0.2.44" not in str(result)
    assert path.read_bytes() == before
    assert not result["save_available"] and not result["commissioning_authorized"]


def test_preview_rejects_unsafe_or_unknown_changes(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"asiair": {"ip_address": "192.0.2.1"},
        "roof": {"source": "alpaca"}}))
    provider = make_setup_provider(path, MonitorBinding("192.0.2.1", "example.org", 443, 17, 5))
    for changes in ({"wave": {"host": "bad"}}, {"asiair": {"ip_address": "secret value"}},
                    {"roof": {"source": "file"}}, {}, {"kasa": {"power_strip_ip": "192.0.2.3"}}):
        result = provider.preview(changes)
        assert not result["ok"] and not result["applied"]
        assert "secret value" not in str(result)
