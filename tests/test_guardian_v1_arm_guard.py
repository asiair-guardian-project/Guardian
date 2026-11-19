"""ARM is refused while Guardian v0.6 runs, and the refusal says why."""
import os

import pytest

from modules.guardian_v1_operator_socket import operator_status
from tests.test_guardian_v1_armed_launch import HARDWARE_TOKEN, env, write_v06  # noqa: F401


def build_ready(env):
    """A hardware-enabled, commissioned monitor, built while v0.6 is NOT running."""
    runner, load, _ = env.build(
        "--commissioning-record", env.sign_off(),
        "--enable-hardware-execution", HARDWARE_TOKEN)
    assert load.usable
    runner.application.mode.enable_hardware_execution()  # what run() does at start
    return runner


def status(runner):
    sock = runner.socket
    return operator_status(sock.app, sock.handler, sock.gate, None, None)


def test_arm_works_when_v06_is_not_running(env):
    runner = build_ready(env)
    assert runner.gate.refusal_reason() is None
    assert status(runner)["arm_available"] is True
    assert runner.gate.arm() is True


def test_arm_is_refused_while_v06_runs_and_says_why(env):
    runner = build_ready(env)
    write_v06(env.root, running=True, pid=os.getpid())
    assert runner.gate.arm() is False
    assert "v0.6" in runner.gate.last_refusal
    assert runner.gate.armed is False
    reply = runner.socket._handle_arm_command({"command": "ARM", "confirmed": True})
    assert reply["ok"] is False and reply["code"] == "ARM_BLOCKED"
    assert "v0.6 is running" in reply["message"]
    s = status(runner)
    assert s["arm_available"] is False and "v0.6" in s["arm_unavailable_reason"]


def test_arm_becomes_possible_once_v06_has_stopped(env):
    runner = build_ready(env)
    write_v06(env.root, running=True, pid=os.getpid())
    assert runner.gate.arm() is False
    write_v06(env.root, running=False, pid=os.getpid())
    assert runner.gate.arm() is True
    assert status(runner)["arm_unavailable_reason"] is None


def test_a_check_that_fails_refuses_arm_instead_of_allowing_it(env):
    runner = build_ready(env)

    def broken():
        raise RuntimeError("cannot read status file")
    runner.gate._arm_blockers = (broken,)
    assert runner.gate.arm() is False
    assert "could not be completed" in runner.gate.last_refusal


def test_monitor_only_says_hardware_is_disabled_by_the_launch_setting(env):
    runner, _load, _ = env.build("--commissioning-record", env.sign_off())
    reason = status(runner)["arm_unavailable_reason"]
    assert "launch setting" in reason and status(runner)["arm_available"] is False


def test_an_uncommissioned_monitor_says_so(env):
    runner, _load, _ = env.build("--enable-hardware-execution", HARDWARE_TOKEN)
    runner.application.mode.enable_hardware_execution()
    assert "Commissioning" in status(runner)["arm_unavailable_reason"]


def test_status_reason_is_hidden_once_armed(env):
    runner = build_ready(env)
    runner.gate.arm()
    s = status(runner)
    assert s["armed"] is True and s["arm_unavailable_reason"] is None


def test_the_app_shows_the_reason():
    from pathlib import Path
    swift = Path("GuardianApp.swift").read_text()
    assert 'status.string("arm_unavailable_reason")' in swift
