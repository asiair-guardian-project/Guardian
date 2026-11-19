from pathlib import Path

from modules.roof_monitor import RoofStatusError, read_roof_status


test_file = Path("tests/sample_roof_status.txt")


def run_test(name, contents=None, create_file=True):
    print(f"\nTEST: {name}")

    if test_file.exists():
        test_file.unlink()

    if create_file:
        test_file.write_text(contents, encoding="utf-8")

    try:
        result = read_roof_status(test_file)
        print(f"Timestamp: {result['timestamp_text']}")
        print(f"Parsed timestamp: {result['timestamp']}")
        print(f"Status: {result['status']}")
        print("RESULT: PASS")
    except RoofStatusError as error:
        print(f"RoofStatusError: {error}")
        print("RESULT: SAFE FAILURE")


run_test(
    "Valid Starfront file",
    "2026-08-07 07:06:59AM CST Roof Status: CLOSED\n",
)

run_test(
    "Missing file",
    create_file=False,
)

run_test(
    "Empty file",
    "",
)

run_test(
    "Malformed file",
    "2026-08-07 07:06:59AM CST Something Else: CLOSED\n",
)

if test_file.exists():
    test_file.unlink()