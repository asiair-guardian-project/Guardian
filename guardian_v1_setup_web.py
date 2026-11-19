"""Start the Guardian 1.0 first-run setup page (local only). Stop it with Ctrl-C.

    .venv/bin/python guardian_v1_setup_web.py [--folder DIR] [--port N]

Then open the printed address in a browser on THIS computer. It reads from your equipment and writes one new
candidate configuration file into the folder (default: the current folder). It never switches power, ARMs,
DISARMs or activates anything.
"""
import argparse
import sys
from pathlib import Path

from modules.guardian_v1_setup_web import DEFAULT_PORT, make_server
from modules.guardian_v1_setup_wizard import CANDIDATE_NAME


def main(argv=None, out=print):
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n")[0])
    parser.add_argument("--folder", default=".", help="where the candidate file is created (default: here)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    folder = Path(args.folder).expanduser().absolute()
    if not folder.is_dir():
        out(f"The folder {folder} does not exist.")
        return 2
    if (folder / CANDIDATE_NAME).exists():
        out(f"{CANDIDATE_NAME} already exists in {folder}. Rename or move it first; this page never overwrites a file.")
        return 2
    try:
        server = make_server(folder, port=args.port)
    except OSError as error:
        out(f"Could not start on port {args.port}: {error}")
        return 2
    port = server.server_address[1]
    out("Guardian 1.0 setup page (this computer only; it cannot switch power or ARM).")
    out(f"Open:  http://127.0.0.1:{port}/")
    out(f"It will create {folder / CANDIDATE_NAME} and nothing else.  Stop with Ctrl-C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
