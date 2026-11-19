#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
command -v swiftc >/dev/null || { echo 'Apple Swift compiler unavailable. Install Xcode Command Line Tools.'; exit 1; }
mkdir -p 'Guardian 1.0.app/Contents/MacOS' 'Guardian 1.0.app/Contents/Resources'
swiftc -parse-as-library -O -framework SwiftUI -framework Foundation -o 'Guardian 1.0.app/Contents/MacOS/GuardianDesktop' GuardianApp.swift
cat > 'Guardian 1.0.app/Contents/Info.plist' <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>GuardianDesktop</string>
<key>CFBundleIdentifier</key><string>local.guardian.v1.desktop.phasec</string>
<key>CFBundleName</key><string>Guardian 1.0</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - 'Guardian 1.0.app'
echo "Built: $PWD/Guardian 1.0.app"
