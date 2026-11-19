#!/bin/zsh
# Guardian v0.6 reset after an aborted session.
#
# WHY: after an emergency abort, v0.6 cannot clear its own block (the ACK button
# in Guardian Control does not do it). Restarting v0.6 does. This script does that
# restart safely. It never cuts or restores power and never ARMs.
#
# Run:  zsh guardian_v06_reset.sh
cd "$(dirname "$0")" || exit 1
LABEL=com.guardian.observatory
UIDN=$(id -u)
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

pid_of() {
  .venv/bin/python - <<'PY' 2>/dev/null
import json
try: print(json.load(open("guardian_status.json")).get("pid",""))
except Exception: print("")
PY
}
alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null; }
protection() { ./guardianctl status 2>/dev/null | sed -n 's/^Protection: //p'; }

echo "=== Guardian v0.6 reset  $(date '+%a %Y-%m-%d %H:%M %Z') ==="

# 1. Never restart a protecting v0.6.
OLD=$(pid_of)
if alive "$OLD"; then
  PROT=$(protection)
  if [ "$PROT" != "DISARMED" ]; then
    echo "REFUSED: v0.6 protection is '${PROT:-UNKNOWN}', not DISARMED."
    echo "Restarting would drop protection. Nothing was changed."
    echo "If you really want to reset: DISARM first in Guardian Control, then run this again."
    exit 1
  fi
  echo "v0.6 is running (PID $OLD) and DISARMED."
else
  echo "v0.6 is not running."
fi

# 2. Make sure the job can be started.
if launchctl print-disabled "gui/$UIDN" 2>/dev/null | grep -q "\"$LABEL\" => disabled"; then
  echo "v0.6 is DISABLED in launchd. Enable and load it first:"
  echo "  launchctl enable gui/$UIDN/$LABEL"
  echo "  launchctl bootstrap gui/$UIDN $PLIST"
  echo "Nothing was changed."
  exit 1
fi
if ! launchctl list 2>/dev/null | grep -q "$LABEL\$"; then
  echo "v0.6 job is not loaded; loading it."
  launchctl bootstrap "gui/$UIDN" "$PLIST" || { echo "FAILED to load v0.6."; exit 1; }
else
  echo "Restarting v0.6."
  launchctl kickstart -k "gui/$UIDN/$LABEL" || { echo "FAILED to restart v0.6."; exit 1; }
fi

# 3. Wait for the new process.
NEW=""
for i in $(seq 1 40); do
  sleep 1
  NEW=$(pid_of)
  if alive "$NEW" && [ "$NEW" != "$OLD" ]; then break; fi
  NEW=""
done
if [ -z "$NEW" ]; then
  echo "RESULT: v0.6 did not come back within 40 s. Check:  tail -20 logs/guardian.log"
  exit 1
fi

PROT=$(protection)
echo "v0.6 restarted: PID $NEW, protection ${PROT:-UNKNOWN}."
curl -s -m 3 http://127.0.0.1:8765/api/status | .venv/bin/python -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit()
if d.get("connected"): print("roof now reads:", (d.get("equipment") or {}).get("roof","unknown"))
' 2>/dev/null
echo
echo "RESULT: reset done. v0.6 is DISARMED and ready."
echo "Now ARM in Guardian Control once the roof reads OPEN (ARM needs a fresh OPEN reading)."
