#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
SRC="tests/fixtures/guardian_v1_demo_abort.json"
if [[ ! -f "$SRC" ]]; then
  echo "Missing demo fixture: $SRC (create with earlier simulated ABORT command)" >&2
  exit 1
fi
TEMP="$(mktemp -d "$PWD/tests/fixtures/.guardian-operator-demo.XXXXXX")"
chmod 700 "$TEMP"
cp "$SRC" "$TEMP/recovery.json"
SOCKET_DIR="$(mktemp -d /tmp/gv1sock.XXXXXX)"
chmod 700 "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/operator.sock"
PID=""
cleanup() {
  if [[ -n "$PID" ]]; then kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; fi
  rm -rf "$TEMP" "$SOCKET_DIR"
}
trap cleanup EXIT
bash desktop_app_v1/build_operator.sh
python guardian_v1_operator_demo.py --fixture "$TEMP/recovery.json" --socket "$SOCKET" &
PID=$!
for i in {1..40}; do
  if [[ -S "$SOCKET" ]]; then break; fi
  sleep 0.1
done
if [[ ! -S "$SOCKET" ]]; then echo 'Demo service failed to start' >&2; exit 1; fi
"$HOME/Desktop/Guardian v1 Operator Recovery.app/Contents/MacOS/GuardianRecovery" "$TEMP/recovery.json" "$SOCKET"
