from pathlib import Path

from modules.control_interface import (
    ControlCommandError,
    clear_control_command,
    read_control_command,
)


test_file = Path("tests/guardian_control_test.txt")


def run_test(command):
    test_file.write_text(
        command,
        encoding="utf-8",
    )

    try:
        result = read_control_command(test_file)
        print(f"Input: {command!r}")
        print(f"Result: {result}")

        clear_control_command(test_file)

        cleared = read_control_command(test_file)
        print(f"After clear: {cleared}")
        print("RESULT: PASS")

    except ControlCommandError as error:
        print(f"Input: {command!r}")
        print(f"ControlCommandError: {error}")
        print("RESULT: SAFE FAILURE")

    print()


run_test("ARM")
run_test("disarm")
run_test("STATUS")
run_test("")
run_test("DO_SOMETHING_DANGEROUS")

if test_file.exists():
    test_file.unlink()