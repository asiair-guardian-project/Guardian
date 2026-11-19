#!/bin/zsh
# Guardian imaging-night check. READ-ONLY: it changes nothing.
# Run:  zsh imaging_check.sh
cd "$(dirname "$0")" || exit 1
UIDN=$(id -u)
problems=()

echo "=== Guardian imaging check  $(date '+%a %Y-%m-%d %H:%M %Z') ==="

# 1. Who is protecting the rig right now?
echo "--- supervisors ---"
SB=$(.venv/bin/python guardian_stage_b.py status 2>&1)
echo "$SB" | grep -v '^PROTECTED_BY:'
BY=$(echo "$SB" | sed -n 's/^PROTECTED_BY: //p')
echo "protected by:    ${BY:-UNKNOWN}"
case "$BY" in
  v0.6|v1.0) ;;
  CONFLICT) problems+=("BOTH v0.6 and v1.0 are armed and able to cut power (DISARM one, or run the Stage B rollback)") ;;
  NONE)     problems+=("nothing is armed (ARM v0.6 in Guardian Control, or ARM v1.0 if you are in Stage B)") ;;
  *)        problems+=("could not tell who is protecting the rig") ;;
esac

# 2. v0.6 job (information; a problem only when v0.6 is the one meant to protect)
if launchctl print-disabled "gui/$UIDN" 2>/dev/null | grep -q '"com.guardian.observatory" => disabled'; then
  echo "v0.6 job:        DISABLED"
  [ "$BY" = "v1.0" ] || problems+=("v0.6 is disabled (enable it, then bootstrap)")
elif launchctl list 2>/dev/null | grep -q 'com.guardian.observatory$'; then
  echo "v0.6 job:        loaded"
else
  echo "v0.6 job:        NOT LOADED"
  [ "$BY" = "v1.0" ] || problems+=("v0.6 is not loaded (bootstrap it)")
fi

# 3. v1.0 pieces
for j in org.guardian.v1.monitor org.guardian.v1.web; do
  if launchctl list 2>/dev/null | grep -q "$j\$"; then echo "$j: loaded"
  else
    echo "$j: NOT LOADED"
    if [ "$j" = "org.guardian.v1.monitor" ] && [ "$BY" = "v1.0" ]; then problems+=("$j is not loaded")
    else problems+=("$j is not loaded (information only unless v1.0 is the protector)"); fi
  fi
done

# 4. What the monitor sees right now
echo "--- v1.0 monitor view ---"
curl -s -m 3 http://127.0.0.1:8765/api/status | .venv/bin/python -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print("no answer from the web page"); sys.exit()
if not d.get("connected"):
    print("NO CONTACT WITH THE v1.0 MONITOR")
else:
    eq=d.get("equipment") or {}
    print("session:  ", d.get("session"))
    print("roof:     ", eq.get("roof", "no recent observation"))
    print("hardware: ", "ENABLED" if d.get("hardware_execution_enabled") else "disabled (watching only)")
    print("last read:", eq.get("observed_at_utc", "unknown"), "(UTC)")
' 2>/dev/null

echo
if [ ${#problems[@]} -eq 0 ]; then
  echo "RESULT: READY - protected by $BY."
else
  echo "RESULT: NOT READY"
  for p in "${problems[@]}"; do echo "  - $p"; done
fi
