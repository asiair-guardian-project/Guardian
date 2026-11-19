"""Save / check the power controller sign-in in the macOS Keychain, without Guardian ever handling the password.

`set`: the user name is passed to `security`; the PASSWORD is typed by the operator directly into macOS's own `security`
prompt (we pass no password and keep the terminal attached), so it never appears in this program, its arguments, the
process list, the configuration or any log. `check`: only asks whether the items exist; never prints a secret.
"""
from __future__ import annotations

import subprocess
from typing import Callable, List

ACCOUNT = "guardian"
SERVICES = {
    "kasa": ("Guardian Kasa Username", "Guardian Kasa Password"),
    "dli": ("Guardian Digital Loggers Username", "Guardian Digital Loggers Password"),
}


class CredentialError(ValueError):
    pass


def _run(cmd: List[str]) -> int:
    return subprocess.run(cmd).returncode           # inherits the terminal: `security` prompts the operator itself


def _run_quiet(cmd: List[str]) -> int:
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def _exists(service: str, run: Callable[[List[str]], int]) -> bool:
    return run(["security", "find-generic-password", "-a", ACCOUNT, "-s", service]) == 0


def set_credentials(kind: str, username: str, run: Callable[[List[str]], int] = None) -> None:
    run = run or _run
    if kind not in SERVICES:
        raise CredentialError("kind must be kasa or dli")
    if not username or not username.strip() or any(ch in username for ch in "\n\r\x00"):
        raise CredentialError("a user name is required")
    user_service, password_service = SERVICES[kind]
    if run(["security", "add-generic-password", "-U", "-a", ACCOUNT, "-s", user_service, "-w", username.strip()]) != 0:
        raise CredentialError("macOS could not save the user name")
    # No password value is given: `security` asks for it on the terminal (hidden) and asks twice.
    if run(["security", "add-generic-password", "-U", "-a", ACCOUNT, "-s", password_service, "-w"]) != 0:
        raise CredentialError("macOS could not save the password (cancelled or the two entries differed)")


def check_credentials(kind: str, run: Callable[[List[str]], int] = None) -> dict:
    run = run or _run_quiet
    if kind not in SERVICES:
        raise CredentialError("kind must be kasa or dli")
    user_service, password_service = SERVICES[kind]
    return {"username": _exists(user_service, run), "password": _exists(password_service, run)}
