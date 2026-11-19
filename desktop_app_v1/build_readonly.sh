#!/bin/bash
set -euo pipefail
# Build only. No launch, no LaunchAgent, no changes to Guardian runtime.
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HOME/Desktop/Guardian v1 Recovery Viewer.app}"
mkdir -p "$OUT/Contents/MacOS"
swiftc "$HERE/GuardianRecovery.swift" -o "$OUT/Contents/MacOS/GuardianRecovery" -framework Cocoa
cat > "$OUT/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Guardian v1 Recovery Viewer</string>
<key>CFBundleIdentifier</key><string>local.guardian.v1.recovery.viewer</string>
<key>CFBundleExecutable</key><string>GuardianRecovery</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
echo "Built: $OUT"
echo "Not launched. Run the binary with an explicit recovery JSON path."
