import os
import stat

import pytest

from modules import guardian_v1_launcher as L
import guardian_v1_launcher as cli


def make(tmp_path, venv=True, config=False, candidate=None, app=False):
    if venv:
        (tmp_path / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / ".venv" / "bin" / "python").write_text("")
    (tmp_path / "config").mkdir(exist_ok=True)
    if config:
        (tmp_path / "config" / "config.yaml").write_text("x: 1\n")
    if candidate:
        (tmp_path / candidate).write_text("x: 1\n")
    if app:
        (tmp_path / L.APP_NAME).mkdir()
    return tmp_path


@pytest.mark.parametrize("kw,expected", [
    (dict(venv=False), L.NO_VENV),
    (dict(), L.SETUP),
    (dict(candidate="config.guardian-candidate.yaml"), L.CANDIDATE_WAITING),
    (dict(candidate="config/config.guardian-candidate.yaml"), L.CANDIDATE_WAITING),
    (dict(config=True), L.BUILD_APP),
    (dict(config=True, app=True), L.OPEN_APP),
    (dict(config=True, candidate="config.guardian-candidate.yaml", app=True), L.OPEN_APP),
])
def test_decide(tmp_path, kw, expected):
    assert L.decide(L.inspect(make(tmp_path, **kw))) == expected


def run(tmp_path, runner_code=0, **kw):
    make(tmp_path, **kw)
    opened, ran, lines, served = [], [], [], []
    result = L.start(tmp_path, opener=lambda t: opened.append(str(t)),
                     runner=lambda a: (ran.append(a), runner_code)[1],
                     serve=lambda f, o, out: served.append(str(f)), out=lines.append)
    return result, opened, ran, "\n".join(lines), served


def test_setup_serves_and_never_builds(tmp_path):
    result, opened, ran, _t, served = run(tmp_path)
    assert result == L.SETUP and served == [str(tmp_path)] and ran == []


def test_open_app_only_opens(tmp_path):
    result, opened, ran, _t, served = run(tmp_path, config=True, app=True)
    assert result == L.OPEN_APP and opened == [str(tmp_path / L.APP_NAME)] and ran == [] and served == []


def test_build_then_open(tmp_path):
    result, opened, ran, _t, _s = run(tmp_path, config=True)
    assert result == L.OPEN_APP and ran == [["/bin/zsh", str(tmp_path / "build_on_mac.sh")]]
    assert opened == [str(tmp_path / L.APP_NAME)]


def test_build_failure_does_not_open(tmp_path):
    result, opened, _r, text, _s = run(tmp_path, runner_code=1, config=True)
    assert result == L.BUILD_APP and opened == [] and "xcode-select" in text


def test_candidate_waiting_points_to_guide_and_changes_nothing(tmp_path):
    before = None
    result, opened, ran, text, served = run(tmp_path, candidate="config.guardian-candidate.yaml")
    assert result == L.CANDIDATE_WAITING and ran == [] and served == []
    assert opened[0].endswith("OPERATOR_GUIDE.md") and not (tmp_path / "config" / "config.yaml").exists()


def test_no_venv_explains(tmp_path):
    result, opened, ran, text, _s = run(tmp_path, venv=False)
    assert result == L.NO_VENV and opened == [] and ran == [] and "not installed" in text


def test_install_writes_executable_script_with_quoted_path(tmp_path):
    folder = tmp_path / "My Guardian Folder"
    folder.mkdir()
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    path = L.install(folder, desktop, out=lambda _t: None)
    text = path.read_text()
    assert path.name == "Start Guardian.command" and os.access(path, os.X_OK)
    assert "'" + str(folder) + "'" in text and text.startswith("#!/bin/zsh")
    assert "guardian_v1_launcher.py start" in text


def test_install_missing_desktop(tmp_path):
    lines = []
    assert L.install(tmp_path, tmp_path / "nope", out=lines.append) is None and lines


def test_cli_where_and_install(tmp_path, monkeypatch):
    lines = []
    assert cli.main(["where"], out=lines.append) == 0 and "Next action" in lines[0]
    d = tmp_path / "D"
    d.mkdir()
    assert cli.main(["install", "--desktop", str(d)], out=lines.append) == 0
    assert (d / "Start Guardian.command").exists()
