#!/usr/bin/env python3
"""Save or check the power controller sign-in in the macOS Keychain.

    .venv/bin/python guardian_v1_credentials.py set kasa      # asks for the user name; macOS asks for the password
    .venv/bin/python guardian_v1_credentials.py set dli
    .venv/bin/python guardian_v1_credentials.py check kasa    # says whether the items exist; never shows them

Guardian never sees the password: you type it into macOS's own hidden prompt.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules.guardian_v1_credentials import CredentialError, check_credentials, set_credentials  # noqa: E402


def main(argv=None, say=print, ask=input, run=None) -> int:
    parser = argparse.ArgumentParser(description="Keychain sign-in for the power controller")
    parser.add_argument("action", choices=["set", "check"])
    parser.add_argument("kind", choices=["kasa", "dli"])
    args = parser.parse_args(argv)
    try:
        if args.action == "check":
            found = check_credentials(args.kind, run)
            say(f"user name saved: {'yes' if found['username'] else 'NO'}; "
                f"password saved: {'yes' if found['password'] else 'NO'}")
            return 0 if all(found.values()) else 1
        username = ask("Controller user name (for Kasa: the account email): ")
        say("macOS will now ask for the password (it is hidden, and asked twice).")
        set_credentials(args.kind, username, run)
    except CredentialError as error:
        say(f"REFUSED: {error}")
        return 1
    say("Saved. Check with:  guardian_v1_credentials.py check " + args.kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
