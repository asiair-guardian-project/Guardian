import sys
import yaml
import pytest
import guardian_v1


def test_compare_cli_never_constructs_application(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump({'asiair': {'ip_address': '192.0.2.1'},
        'roof': {'source': 'alpaca', 'alpaca_host': '192.0.2.2',
                 'alpaca_port': 11111, 'alpaca_device_number': 17},
        'monitor': {'interval_seconds': 5}}))
    def forbidden(**kwargs):
        raise AssertionError('application must not start')
    monkeypatch.setattr(guardian_v1, 'build_application', forbidden)
    monkeypatch.setattr(sys, 'argv', ['guardian_v1.py', '--check-installation-config', str(path),
        '--asiair-host', '192.0.2.1', '--alpaca-host', '192.0.2.2', '--alpaca-port', '11111'])
    guardian_v1.main()
    assert 'commissioning NOT AUTHORIZED' in capsys.readouterr().out
    monkeypatch.setattr(sys, 'argv', ['guardian_v1.py', '--check-installation-config', str(path),
        '--asiair-host', '192.0.2.9', '--alpaca-host', '192.0.2.2', '--alpaca-port', '11111'])
    with pytest.raises(SystemExit) as exc:
        guardian_v1.main()
    assert exc.value.code == 2
    assert 'MISMATCH' in capsys.readouterr().out
