import guardian_v1


def test_guardian_v1_parser_identifies_shadow_mode():
    parser = guardian_v1.build_parser()
    args = parser.parse_args([])

    assert args.shadow is True


def test_guardian_v1_has_no_armed_option():
    parser = guardian_v1.build_parser()

    try:
        parser.parse_args(["--armed"])
    except SystemExit:
        pass
    else:
        raise AssertionError(
            "Guardian 1.0 shadow entry point must not accept --armed"
        )


def test_guardian_v1_application_starts_monitor_only():
    app = guardian_v1.build_application()

    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_entrypoint_missing_recovery_file_blocks_arm(tmp_path):
    app = guardian_v1.build_application(recovery_file=tmp_path / "missing.json")
    assert app.mode.hardware_execution_enabled is False
    assert app.supervisor.recovery_blocked is True
    assert app.supervisor.incident is None


def test_entrypoint_status_is_read_only(tmp_path, capsys, monkeypatch):
    path = tmp_path / "missing.json"
    monkeypatch.setattr("sys.argv", ["guardian_v1.py", "--status", "--recovery-file", str(path)])
    guardian_v1.main()
    output = capsys.readouterr().out
    assert "ARM blocked: True" in output
    assert "Hardware execution: DISABLED" in output
    assert not path.exists()


def test_entrypoint_status_without_store_is_explicit(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["guardian_v1.py", "--status"])
    guardian_v1.main()
    assert "NOT CONFIGURED" in capsys.readouterr().out
