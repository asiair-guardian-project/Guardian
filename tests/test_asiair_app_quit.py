from unittest.mock import patch

from modules.guardian import Guardian


class Result:
    def __init__(self, returncode=0):
        self.returncode = returncode


guardian = Guardian()

with patch("modules.guardian.subprocess.run") as run:
    run.return_value = Result(returncode=1)

    assert guardian.quit_asiair_app() is True
    assert run.call_count == 1
    assert run.call_args.args[0] == ["pgrep", "-x", "ASIAIR2"]

print("PASS: already-closed ASIAIR2 is a successful no-op")


with patch("modules.guardian.subprocess.run") as run:
    run.side_effect = [
        Result(returncode=0),
        Result(returncode=0),
    ]

    assert guardian.quit_asiair_app() is True
    assert run.call_count == 2

    quit_command = run.call_args_list[1].args[0]

    assert quit_command == [
        "osascript",
        "-e",
        'tell application "ASIAIR2" to quit',
    ]

print("PASS: running ASIAIR2 receives graceful quit")


with patch("modules.guardian.subprocess.run") as run:
    run.side_effect = [
        Result(returncode=0),
        RuntimeError("test AppleScript failure"),
    ]

    assert guardian.quit_asiair_app() is False

print("PASS: ASIAIR2 quit failure does not raise")
