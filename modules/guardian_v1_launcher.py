"""One-click starter for Guardian 1.0 (macOS).

`install` puts a double-clickable "Start Guardian.command" on the Desktop. Double-clicking it runs `start`, which
looks at where this installation is up to and does the one sensible next thing:

  no configuration yet        -> opens the local setup page in your browser
  setup file waiting          -> tells you the next step (does not touch your files)
  configuration, app not built-> builds the Guardian app (needs Xcode command line tools)
  app built                   -> opens the Guardian app

It never switches power, ARMs, DISARMs or changes any configuration file.
"""
import os
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

LAUNCHER_NAME = "Start Guardian.command"
APP_NAME = "Guardian 1.0.app"
CONFIG = Path("config") / "config.yaml"
CANDIDATE = Path("config.guardian-candidate.yaml")
CANDIDATE_IN_CONFIG = Path("config") / "config.guardian-candidate.yaml"

SETUP, CANDIDATE_WAITING, BUILD_APP, OPEN_APP, NO_VENV = (
    "SETUP", "CANDIDATE_WAITING", "BUILD_APP", "OPEN_APP", "NO_VENV")


@dataclass(frozen=True)
class State:
    has_venv: bool
    has_config: bool
    candidate: str  # "" or the candidate file's path relative to the folder
    has_app: bool


def inspect(folder):
    folder = Path(folder)
    candidate = next((str(p) for p in (CANDIDATE, CANDIDATE_IN_CONFIG) if (folder / p).exists()), "")
    return State((folder / ".venv" / "bin" / "python").exists(), (folder / CONFIG).exists(),
                 candidate, (folder / APP_NAME).exists())


def decide(state):
    if not state.has_venv:
        return NO_VENV
    if state.has_config:
        return OPEN_APP if state.has_app else BUILD_APP
    return CANDIDATE_WAITING if state.candidate else SETUP


def start(folder, *, opener=None, runner=None, serve=None, out=print):
    """Do the next sensible thing. opener/runner/serve are injectable for tests."""
    folder = Path(folder).expanduser().absolute()
    opener = opener or (lambda target: subprocess.run(["open", str(target)], check=False).returncode)
    runner = runner or (lambda argv: subprocess.run(argv, cwd=folder, check=False).returncode)
    state = inspect(folder)
    action = decide(state)
    guide = folder / "docs" / "OPERATOR_GUIDE.md"
    if action == NO_VENV:
        out("Guardian is not installed on this Mac yet (its Python environment is missing).")
        out(f"Follow 'What you need' in {guide} first, then double-click this again.")
        return action
    if action == SETUP:
        out("Welcome to Guardian. There is no configuration yet, so this opens the setup page.")
        out("Keep this window open while you use the page; close it when you finish setup.")
        return (serve or _serve_setup)(folder, opener, out) or action
    if action == CANDIDATE_WAITING:
        out(f"Setup has already written {state.candidate}.")
        out("Next: review it, then follow step 1 of 'Setting up' in the operator guide to put it in place:")
        out(f"  {guide}")
        opener(guide)
        return action
    if action == BUILD_APP:
        out("Your configuration is in place. Building the Guardian app (about a minute)...")
        code = runner(["/bin/zsh", str(folder / "build_on_mac.sh")])
        if code != 0:
            out("The app could not be built. If it mentions Swift, run  xcode-select --install  and try again.")
            return action
        out("Built. Opening Guardian...")
        opener(folder / APP_NAME)
        return OPEN_APP
    out("Opening Guardian. You can close this window.")
    opener(folder / APP_NAME)
    return action


def _serve_setup(folder, opener, out):
    from modules.guardian_v1_setup_web import DEFAULT_PORT, make_server
    try:
        server = make_server(folder, port=DEFAULT_PORT)
    except OSError:
        url = f"http://127.0.0.1:{DEFAULT_PORT}/"
        out(f"The setup page is already running. Opening {url}")
        opener(url)
        return SETUP
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    out(f"Setup page: {url}  (this Mac only)")
    opener(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return SETUP


def launcher_script(folder):
    return ("#!/bin/zsh\n"
            f"cd {shlex.quote(str(folder))} || {{ echo 'Guardian folder not found. Was it moved?'; exit 1; }}\n"
            ".venv/bin/python guardian_v1_launcher.py start\n")


def install(folder, desktop=None, out=print):
    """Write the desktop launcher. Never overwrites a different file silently: it replaces only its own."""
    folder = Path(folder).expanduser().absolute()
    desktop = Path(desktop).expanduser() if desktop else Path.home() / "Desktop"
    if not desktop.is_dir():
        out(f"The folder {desktop} does not exist.")
        return None
    path = desktop / LAUNCHER_NAME
    path.write_text(launcher_script(folder), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    out(f"Created {path}")
    out("Double-click it any time to open Guardian (or to continue setup).")
    out("If macOS blocks it the first time: right-click it, choose Open, then Open again.")
    return path
